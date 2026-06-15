"""
geophyto_qa.lookalike.clip_confuse
=================================
Level-1 (image) look-alike test. Embed Bugwood photos of each disease class with
a CLIP image encoder and measure how visually entangled two classes ON THE SAME
CROP are. Because both members share the crop, the comparison isolates *disease
appearance*, not crop.

Confusability metrics for a pair (A, B):
  * cross_knn_rate : pool A∪B; for each image its nearest neighbor (excluding
                     itself) — fraction whose NN belongs to the OTHER class.
                     0.5 == fully intermixed; ~0 == cleanly separable. THIS is
                     the gate metric.
  * centroid_sim   : cosine(mean(A), mean(B)). INFORMATIONAL ONLY — raw CLIP
                     cosine is globally saturated (~0.9 for any two leaf-photo
                     sets), so it does not discriminate and is NOT gated on.
  * sep_ratio      : mean cross-class sim / mean within-class sim (~1 for all
                     here → confirms coarse entanglement; informational).

A pair is image-confusable when cross_knn_rate >= --knn-thresh (tunable).

Caveat: cross_knn is deflated when the two diseases are photographed on
DIFFERENT organs (e.g. one on fruit, one on leaves) — whole-image CLIP then
separates them by organ even if the symptoms are conceptually confused. Such
pairs read as image-separable; tune --knn-thresh or pre-filter by descriptor.

Embeddings are cached per image number so re-runs and the full sweep are cheap.
Runs on CPU (small sample) or GPU (full corpus, via the sbatch wrapper).

CLI:
  python -m geophyto_qa.lookalike.clip_confuse \
      --pairs geophyto_qa/pairs/candidates.json --per-class 24 \
      --out geophyto_qa/lookalike/clip_scores.json [--top 40]
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import urllib.request

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
ROOT = os.path.dirname(PKG)
sys.path.insert(0, ROOT)
from geophyto_qa.data_source import (                   # noqa: E402
    DEFAULT_SOURCE, load_class_images as ds_class_images, fetch_locator, read_image_bytes)

EMB_CACHE = os.path.join(HERE, "emb_cache")

# Coarse organ / presentation bucket per descriptor. Organ-matched confusability
# only compares images SHARING a bucket. (An ImageFolder has no organ metadata, so
# everything falls in one "symptom" bucket and organ-matching is a no-op there.)
ORGAN_BUCKET = {
    "Foliage": "leaf", "Symptoms": "symptom", "Sign": "sign",
    "Fruit(s)": "fruit", "Fruiting Bodies": "sign",
    "Asexual Spore": "sign", "Sexual Spore": "sign",
    "Stem(s)": "stem", "Seedling(s)": "seedling", "Plant(s)": "whole",
    "Research": "symptom",
}


def organ_bucket(descriptor: str) -> str:
    return ORGAN_BUCKET.get((descriptor or "").strip(), (descriptor or "other").strip().lower())


# --------------------------------------------------------------------------- #
def _load_model(model_name, pretrained, device):
    import open_clip
    import torch
    model, _, preprocess = open_clip.create_model_and_transforms(
        model_name, pretrained=pretrained)
    model.eval().to(device)
    return model, preprocess, torch


def _cache_key(n):
    import hashlib
    return hashlib.sha1(str(n).encode()).hexdigest()


def embed_images(imgnums, locator, model, preprocess, torch, device, log_every=50, workers=12):
    """Return {img_id: 1-D np.float32 embedding} with on-disk caching.

    Image reads (local disk) are I/O-bound and run concurrently in a thread pool;
    CLIP encoding runs on the main thread as each image arrives. `locator` maps
    img_id -> local path (or URL)."""
    os.makedirs(EMB_CACHE, exist_ok=True)
    from io import BytesIO
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from PIL import Image
    out = {}
    todo = []
    for n in imgnums:
        cp = os.path.join(EMB_CACHE, f"{_cache_key(n)}.npy")
        if os.path.exists(cp):
            out[n] = np.load(cp)
        else:
            todo.append(n)
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(read_image_bytes, locator[n]): n for n in todo}
        for fut in as_completed(futs):
            n = futs[fut]
            raw = fut.result()
            if raw is None:
                continue
            try:
                img = Image.open(BytesIO(raw)).convert("RGB")
                x = preprocess(img).unsqueeze(0).to(device)
                with torch.no_grad():
                    v = model.encode_image(x)[0].float().cpu().numpy()
                v = v / (np.linalg.norm(v) + 1e-8)
                np.save(os.path.join(EMB_CACHE, f"{_cache_key(n)}.npy"), v.astype(np.float32))
                out[n] = v.astype(np.float32)
            except Exception:
                continue
            done += 1
            if done % log_every == 0:
                print(f"  embedded {done}/{len(todo)} new images", flush=True)
    return out


def _cross_knn(A: np.ndarray, B: np.ndarray) -> float:
    """Fraction of pooled images whose nearest neighbor is the OTHER class."""
    X = np.vstack([A, B])
    lab = np.array([0] * len(A) + [1] * len(B))
    S = X @ X.T
    np.fill_diagonal(S, -1.0)
    nn = S.argmax(1)
    return float(np.mean(lab[nn] != lab))


def confusability_matched(A_by: dict, B_by: dict, knn_thresh: float,
                          min_side: int = 4, min_support: int = 5) -> dict:
    """Organ-matched confusability.

    A_by / B_by : {organ_bucket: (n,d) embedding matrix} for the two classes.
    Compares ONLY within shared buckets (each side >= min_side), then aggregates
    cross-kNN weighted by balanced support. A pair with no shared, sufficiently
    populated organ bucket cannot be visually confirmed as a look-alike.
    """
    shared = [b for b in (set(A_by) & set(B_by))
              if len(A_by[b]) >= min_side and len(B_by[b]) >= min_side]
    if not shared:
        return {"ok": False, "reason": "no shared-organ support",
                "shared_buckets": []}
    per = {}
    wsum = 0.0
    knn_acc = 0.0
    for b in sorted(shared):
        Ab, Bb = A_by[b], B_by[b]
        w = min(len(Ab), len(Bb))
        knn = _cross_knn(Ab, Bb)
        per[b] = {"cross_knn": round(knn, 4), "n_a": len(Ab), "n_b": len(Bb)}
        knn_acc += w * knn
        wsum += w
    matched_knn = knn_acc / wsum if wsum else 0.0
    support = int(wsum)
    return {"ok": support >= min_support,
            "reason": None if support >= min_support else "insufficient matched support",
            "matched_cross_knn": round(matched_knn, 4),
            "matched_support": support,
            "shared_buckets": sorted(shared),
            "by_bucket": per}


def confusability(A: np.ndarray, B: np.ndarray) -> dict:
    """A, B: (n, d) L2-normalized embedding matrices for the two classes."""
    if len(A) < 3 or len(B) < 3:
        return {"ok": False, "reason": "too few embeddings"}
    ca, cb = A.mean(0), B.mean(0)
    ca /= np.linalg.norm(ca) + 1e-8
    cb /= np.linalg.norm(cb) + 1e-8
    centroid_sim = float(ca @ cb)

    X = np.vstack([A, B])
    lab = np.array([0] * len(A) + [1] * len(B))
    S = X @ X.T
    np.fill_diagonal(S, -1.0)               # exclude self
    nn = S.argmax(1)
    cross = float(np.mean(lab[nn] != lab))   # NN in the other class

    # within vs cross mean similarity (upper-tri only, exclude self)
    within = []
    crosss = []
    n = len(X)
    for i in range(n):
        for j in range(i + 1, n):
            (within if lab[i] == lab[j] else crosss).append(S[i, j] if S[i, j] > -1 else X[i] @ X[j])
    mw = float(np.mean(within)) if within else 0.0
    mc = float(np.mean(crosss)) if crosss else 0.0
    sep_ratio = float(mc / mw) if mw > 0 else 0.0
    return {"ok": True, "n_a": len(A), "n_b": len(B),
            "centroid_sim": round(centroid_sim, 4),
            "cross_knn_rate": round(cross, 4),
            "sep_ratio": round(sep_ratio, 4),
            "within_sim": round(mw, 4), "cross_sim": round(mc, 4)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=DEFAULT_SOURCE,
                    help="ImageFolder dataset dir (default: GPQA_SOURCE / CyAg)")
    ap.add_argument("--pairs", default=os.path.join(PKG, "pairs", "candidates.json"))
    ap.add_argument("--per-class", type=int, default=24, help="image cap per class (None=all via 0)")
    ap.add_argument("--top", type=int, default=None, help="only score the top-N ranked candidate pairs")
    ap.add_argument("--model", default="ViT-B-32")
    ap.add_argument("--pretrained", default="openai")
    ap.add_argument("--knn-thresh", type=float, default=0.12,
                    help="min cross-kNN rate to call a pair image-confusable")
    ap.add_argument("--match-mode", choices=["organ", "whole"], default="organ",
                    help="organ = compare within shared organ buckets (default); whole = whole-image")
    ap.add_argument("--min-side", type=int, default=4, help="min imgs per side per organ bucket")
    ap.add_argument("--min-support", type=int, default=5, help="min matched support to gate on organ score")
    ap.add_argument("--out", default=os.path.join(HERE, "clip_scores.json"))
    args = ap.parse_args()

    pairs = json.load(open(args.pairs))["pairs"]
    if args.top:
        pairs = pairs[:args.top]
    cap = args.per_class or None

    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"CLIP {args.model}/{args.pretrained} on {device}; scoring {len(pairs)} pairs "
          f"(per_class={cap})", flush=True)
    model, preprocess, torch = _load_model(args.model, args.pretrained, device)

    class_imgs = ds_class_images(args.source, cap)
    locator = fetch_locator(args.source)
    # gather every image we need
    need = set()
    for p in pairs:
        for m in ("member_a", "member_b"):
            need |= {n for n, _ in class_imgs.get((p["crop"], p[m]["disease"]), [])}
    print(f"embedding up to {len(need)} images ...", flush=True)
    emb = embed_images(sorted(need), locator, model, preprocess, torch, device)

    def mat(crop, dis):
        v = [emb[n] for n, _ in class_imgs.get((crop, dis), []) if n in emb]
        return np.vstack(v) if v else np.zeros((0, 1))

    def by_organ(crop, dis):
        buckets = collections.defaultdict(list)
        for n, org in class_imgs.get((crop, dis), []):
            if n in emb:
                buckets[org].append(emb[n])
        return {b: np.vstack(v) for b, v in buckets.items()}

    results = {}
    for p in pairs:
        A = mat(p["crop"], p["member_a"]["disease"])
        B = mat(p["crop"], p["member_b"]["disease"])
        whole = confusability(A, B) if (len(A) and len(B)) else {"ok": False, "reason": "no images"}
        matched = confusability_matched(by_organ(p["crop"], p["member_a"]["disease"]),
                                        by_organ(p["crop"], p["member_b"]["disease"]),
                                        args.knn_thresh, args.min_side, args.min_support)
        c = dict(whole)
        c["whole_image_cross_knn"] = whole.get("cross_knn_rate")
        c["matched"] = matched
        if args.match_mode == "organ":
            c["image_confusable"] = bool(matched.get("ok")
                                         and matched["matched_cross_knn"] >= args.knn_thresh)
            c["gate_cross_knn"] = matched.get("matched_cross_knn")
        else:
            c["image_confusable"] = bool(whole.get("ok")
                                         and whole["cross_knn_rate"] >= args.knn_thresh)
            c["gate_cross_knn"] = whole.get("cross_knn_rate")
        results[p["pair_id"]] = c

    n_ok = sum(1 for c in results.values() if c.get("image_confusable"))
    with open(args.out, "w") as fh:
        json.dump({"model": f"{args.model}/{args.pretrained}",
                   "per_class": cap, "knn_thresh": args.knn_thresh,
                   "match_mode": args.match_mode, "min_side": args.min_side,
                   "min_support": args.min_support,
                   "gate_metric": "matched_cross_knn" if args.match_mode == "organ" else "cross_knn_rate",
                   "scores": results}, fh, indent=2)
    print(f"image-confusable ({args.match_mode}): {n_ok}/{len(results)} pairs -> {args.out}", flush=True)
    for pid, c in list(results.items())[:14]:
        m = c.get("matched", {})
        gk = c.get("gate_cross_knn")
        print(f"  {'YES' if c['image_confusable'] else ' no'} "
              f"gate_knn={gk if gk is not None else '-'} "
              f"whole={c.get('whole_image_cross_knn','-')} "
              f"sup={m.get('matched_support','-')} buckets={m.get('shared_buckets',[])} {pid}")


if __name__ == "__main__":
    main()
