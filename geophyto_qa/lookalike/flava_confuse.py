"""
geophyto_qa.lookalike.flava_confuse
===================================
Level-1 (image) look-alike test with a NATIVELY-MULTIMODAL encoder (FLAVA),
replacing the CLIP dual-encoder. CLIP fuses image and text only LATE (cosine of
two separate towers); FLAVA embeds images through a unified multimodal
transformer, so "hard to tell apart for FLAVA" is a stronger, more defensible
notion of confusability than CLIP cross-kNN.

Confusability = BIDIRECTIONAL ENTAILMENT (not the symmetric blend CLIP used).
For two classes A, B sharing a crop+organ bucket, with L2-normalized FLAVA
image embeddings:

  entail(A->B) : fraction of A's images whose nearest neighbor (in A u B,
                 excluding self) belongs to class B  -- "A is covered by B".
  entail(B->A) : the reverse.
  bidir        : min(entail(A->B), entail(B->A))     -- BOTH directions must
                 hold. A pair where A's photos all look like B but B's are
                 distinctive (one-directional) is NOT a true mutual look-alike
                 and scores low here, unlike a symmetric pooled rate.

This is the same bidirectional-entailment criterion used to cluster
semantically-equivalent text (A entails B AND B entails A); here the "entailment"
is image-neighborhood coverage in FLAVA space.

Role (unchanged from CLIP): web confirmation is the GATE; this score is the
ROUTER + auditable evidence. It never vetoes a web-confirmed pair, it only labels
the lane (>= gate -> image_ambiguous / Lane B; < gate -> image_decisive / Lane A).
Output schema matches clip_scores.json (`matched.matched_cross_knn` carries the
bidirectional score) so geophyto_qa.lookalike.verify_pairs consumes it unchanged.

Embeddings are cached per image number under a FLAVA-namespaced dir so they never
mix with CLIP's cache. CPU for a small sample; GPU for the full sweep.

CLI:
  python -m geophyto_qa.lookalike.flava_confuse \
      --pairs geophyto_qa/pairs/candidates.json --per-class 24 \
      --out geophyto_qa/lookalike/flava_scores.json [--top 40]
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
ROOT = os.path.dirname(PKG)
sys.path.insert(0, ROOT)

# Reuse the encoder-agnostic machinery (organ buckets, image fetch, class roster).
from geophyto_qa.lookalike.clip_confuse import (   # noqa: E402
    organ_bucket, _fetch, load_class_images, DEFAULT_CSV,
)

MODEL_ID = "facebook/flava-full"
EMB_CACHE = os.path.join(HERE, "emb_cache_flava")   # FLAVA-namespaced; never mixes with CLIP


# --------------------------------------------------------------------------- #
def _load_flava(device):
    """Return (model, processor, torch). Image embedding = image-encoder CLS token."""
    import torch
    from transformers import FlavaModel, FlavaProcessor
    model = FlavaModel.from_pretrained(MODEL_ID).eval().to(device)
    proc = FlavaProcessor.from_pretrained(MODEL_ID)
    return model, proc, torch


def embed_images(imgnums, model, proc, torch, device, log_every=50, workers=12):
    """{imgnum: 1-D np.float32 FLAVA image embedding (CLS, L2-normalized)} with cache."""
    os.makedirs(EMB_CACHE, exist_ok=True)
    from io import BytesIO
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from PIL import Image
    out, todo = {}, []
    for n in imgnums:
        cp = os.path.join(EMB_CACHE, f"{n}.npy")
        if os.path.exists(cp):
            out[n] = np.load(cp)
        else:
            todo.append(n)
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_fetch, n): n for n in todo}
        for fut in as_completed(futs):
            n = futs[fut]
            raw = fut.result()
            if raw is None:
                continue
            try:
                img = Image.open(BytesIO(raw)).convert("RGB")
                inputs = proc(images=img, return_tensors="pt").to(device)
                with torch.no_grad():
                    feats = model.get_image_features(pixel_values=inputs["pixel_values"])
                v = feats[0, 0].float().cpu().numpy()        # CLS token of the image encoder
                v = v / (np.linalg.norm(v) + 1e-8)
                np.save(os.path.join(EMB_CACHE, f"{n}.npy"), v.astype(np.float32))
                out[n] = v.astype(np.float32)
            except Exception:
                continue
            done += 1
            if done % log_every == 0:
                print(f"  embedded {done}/{len(todo)} new images", flush=True)
    return out


# --------------------------------------------------------------------------- #
def _directional_knn(A: np.ndarray, B: np.ndarray) -> tuple[float, float]:
    """(entail A->B, entail B->A): fraction of each class whose NN is the OTHER class."""
    X = np.vstack([A, B])
    na = len(A)
    lab = np.array([0] * na + [1] * len(B))
    S = X @ X.T
    np.fill_diagonal(S, -1.0)                 # exclude self
    nn = lab[S.argmax(1)]
    a2b = float(np.mean(nn[:na] == 1)) if na else 0.0     # A's NN lands in B
    b2a = float(np.mean(nn[na:] == 0)) if len(B) else 0.0  # B's NN lands in A
    return a2b, b2a


def bidir_matched(A_by: dict, B_by: dict, min_side: int = 4, min_support: int = 5) -> dict:
    """Organ-matched BIDIRECTIONAL entailment confusability.

    Compares only within shared organ buckets (each side >= min_side), aggregates
    each direction weighted by balanced support, then takes min -> bidir score.
    """
    shared = [b for b in (set(A_by) & set(B_by))
              if len(A_by[b]) >= min_side and len(B_by[b]) >= min_side]
    if not shared:
        return {"ok": False, "reason": "no shared-organ support", "shared_buckets": []}
    per, wsum, a_acc, b_acc = {}, 0.0, 0.0, 0.0
    for b in sorted(shared):
        Ab, Bb = A_by[b], B_by[b]
        w = min(len(Ab), len(Bb))
        a2b, b2a = _directional_knn(Ab, Bb)
        per[b] = {"entail_ab": round(a2b, 4), "entail_ba": round(b2a, 4),
                  "bidir": round(min(a2b, b2a), 4), "n_a": len(Ab), "n_b": len(Bb)}
        a_acc += w * a2b
        b_acc += w * b2a
        wsum += w
    ab = a_acc / wsum if wsum else 0.0
    ba = b_acc / wsum if wsum else 0.0
    support = int(wsum)
    return {"ok": support >= min_support,
            "reason": None if support >= min_support else "insufficient matched support",
            "matched_entail_ab": round(ab, 4),
            "matched_entail_ba": round(ba, 4),
            # bidirectional confusability = both directions must hold:
            "matched_cross_knn": round(min(ab, ba), 4),
            "matched_support": support,
            "shared_buckets": sorted(shared),
            "by_bucket": per}


def bidir_whole(A: np.ndarray, B: np.ndarray) -> dict:
    """Whole-image bidirectional entailment (informational, like CLIP's whole lane)."""
    if len(A) < 3 or len(B) < 3:
        return {"ok": False, "reason": "too few embeddings"}
    a2b, b2a = _directional_knn(A, B)
    ca, cb = A.mean(0), B.mean(0)
    ca /= np.linalg.norm(ca) + 1e-8
    cb /= np.linalg.norm(cb) + 1e-8
    return {"ok": True, "n_a": len(A), "n_b": len(B),
            "centroid_sim": round(float(ca @ cb), 4),
            "entail_ab": round(a2b, 4), "entail_ba": round(b2a, 4),
            "cross_knn_rate": round(min(a2b, b2a), 4)}   # bidir; named to match downstream


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=DEFAULT_CSV)
    ap.add_argument("--pairs", default=os.path.join(PKG, "pairs", "candidates.json"))
    ap.add_argument("--per-class", type=int, default=24, help="image cap per class (0=all)")
    ap.add_argument("--top", type=int, default=None, help="only score the top-N ranked pairs")
    ap.add_argument("--knn-gate", type=float, default=0.20,
                    help="min bidirectional score to route a pair into Lane B (image_ambiguous)")
    ap.add_argument("--match-mode", choices=["organ", "whole"], default="organ")
    ap.add_argument("--min-side", type=int, default=4)
    ap.add_argument("--min-support", type=int, default=5)
    ap.add_argument("--out", default=os.path.join(HERE, "flava_scores.json"))
    args = ap.parse_args()

    pairs = json.load(open(args.pairs))["pairs"]
    if args.top:
        pairs = pairs[:args.top]
    cap = args.per_class or None

    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"FLAVA {MODEL_ID} on {device}; scoring {len(pairs)} pairs (per_class={cap}); "
          f"metric=bidirectional_entailment_knn", flush=True)
    model, proc, torch = _load_flava(device)

    class_imgs = load_class_images(args.csv, cap)
    need = set()
    for p in pairs:
        for m in ("member_a", "member_b"):
            need |= {n for n, _ in class_imgs.get((p["crop"], p[m]["disease"]), [])}
    print(f"embedding up to {len(need)} images ...", flush=True)
    emb = embed_images(sorted(need), model, proc, torch, device)

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
        da, db = p["member_a"]["disease"], p["member_b"]["disease"]
        A, B = mat(p["crop"], da), mat(p["crop"], db)
        whole = bidir_whole(A, B) if (len(A) and len(B)) else {"ok": False, "reason": "no images"}
        matched = bidir_matched(by_organ(p["crop"], da), by_organ(p["crop"], db),
                                args.min_side, args.min_support)
        c = dict(whole)
        c["whole_image_cross_knn"] = whole.get("cross_knn_rate")
        c["matched"] = matched
        if args.match_mode == "organ":
            c["image_confusable"] = bool(matched.get("ok")
                                         and matched["matched_cross_knn"] >= args.knn_gate)
            c["gate_cross_knn"] = matched.get("matched_cross_knn")
        else:
            c["image_confusable"] = bool(whole.get("ok")
                                         and whole["cross_knn_rate"] >= args.knn_gate)
            c["gate_cross_knn"] = whole.get("cross_knn_rate")
        results[p["pair_id"]] = c

    n_ok = sum(1 for c in results.values() if c.get("image_confusable"))
    with open(args.out, "w") as fh:
        json.dump({"encoder": MODEL_ID,
                   "metric": "bidirectional_entailment_knn",
                   "per_class": cap, "knn_gate": args.knn_gate,
                   "match_mode": args.match_mode, "min_side": args.min_side,
                   "min_support": args.min_support,
                   "gate_metric": "matched_cross_knn (bidirectional)",
                   "scores": results}, fh, indent=2)
    print(f"image-confusable / bidir>=gate ({args.match_mode}): {n_ok}/{len(results)} pairs "
          f"-> {args.out}", flush=True)
    for pid, c in list(results.items())[:14]:
        m = c.get("matched", {})
        print(f"  bidir={m.get('matched_cross_knn')}  "
              f"(a->b={m.get('matched_entail_ab')}, b->a={m.get('matched_entail_ba')})  "
              f"buckets={m.get('shared_buckets')}  {pid}", flush=True)


if __name__ == "__main__":
    main()
