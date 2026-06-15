"""
geophyto_qa.lookalike.identify_pairs
====================================
WEB-FIRST sweep step 0 — *identify all candidate pairs first*, reproducibly,
and emit the web-verification worklist.

This is the entry point for the web-gate / CLIP-router pipeline. It does NOT call
any model or network: it deterministically mines every within-crop candidate
look-alike pair from the enriched CSV, joins whatever web + CLIP evidence already
exists, and writes a single auditable manifest plus the list of pairs that still
need a web check (the full-sweep work-list).

Reproducible: pure function of (CSV, --min-imgs); pairs are mined and sorted
deterministically by mine_pairs.mine, and no randomness is used here.

Outputs (under geophyto_qa/pairs/):
  candidates.json    full mined candidate set ({min_imgs, n_pairs, pairs})
  pair_manifest.json one row per pair: ids, image counts, web status, CLIP lane
  needs_web.json     pair_ids (+ minimal context) still needing a web check

CLI:
  python -m geophyto_qa.lookalike.identify_pairs --min-imgs 12
"""
from __future__ import annotations

import argparse
import csv as csvmod
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
ROOT = os.path.dirname(PKG)
sys.path.insert(0, ROOT)

from geophyto_qa.mine_pairs import mine                          # noqa: E402
from geophyto_qa.data_source import load_rows, DEFAULT_SOURCE    # noqa: E402
from geophyto_qa.lookalike.verify_pairs import clip_lane_hint, KNN_GATE  # noqa: E402

PAIRS_DIR = os.path.join(PKG, "pairs")
WEB_PATH = os.path.join(HERE, "web_evidence.json")
CLIP_PATH = os.path.join(HERE, "clip_scores.json")


def _load(path, key=None):
    if not os.path.exists(path):
        return {}
    d = json.load(open(path))
    return d.get(key, {}) if key else d


def identify(source=DEFAULT_SOURCE, min_imgs=12, knn_gate=KNN_GATE,
             web_path=WEB_PATH, clip_path=CLIP_PATH):
    rows = load_rows(source)
    pairs = mine(rows, min_imgs)                 # deterministic, sorted by prior
    web = _load(web_path)
    clip = _load(clip_path, "scores")

    manifest = []
    for p in pairs:
        pid = p["pair_id"]
        w = web.get(pid, {})
        c = clip.get(pid, {})
        mk = (c.get("matched", {}) or {}).get("matched_cross_knn")
        web_checked = "verified" in w
        web_ok = bool(w.get("verified"))
        manifest.append({
            "pair_id": pid,
            "crop": p["crop"],
            "member_a": p["member_a"]["disease"],
            "member_b": p["member_b"]["disease"],
            "n_imgs_a": p["member_a"]["n_imgs"],
            "n_imgs_b": p["member_b"]["n_imgs"],
            "n_imgs_total": p["member_a"]["n_imgs"] + p["member_b"]["n_imgs"],
            "lookalike_prior": p["lookalike_prior"],
            "same_pathogen_class": p["same_pathogen_class"],
            "shared_descriptors": p["shared_descriptors"],
            # WEB GATE state
            "web_checked": web_checked,
            "web_verified": web_ok,
            "confirmed": web_ok,                 # web is the gate
            "web_source_url": w.get("source_url"),
            # CLIP ROUTER state
            "clip_scored": mk is not None,
            "matched_cross_knn": mk,
            "clip_lane_hint": clip_lane_hint(mk, knn_gate),
            "needs_web": not web_checked,        # the full-sweep work item
        })
    return manifest


def write_outputs(manifest, min_imgs, out_dir=PAIRS_DIR):
    os.makedirs(out_dir, exist_ok=True)
    # restore the full candidates.json (it had been overwritten to 3 entries)
    cand = [{k: m[k] for k in ("pair_id", "crop", "member_a", "member_b",
                               "n_imgs_a", "n_imgs_b", "lookalike_prior",
                               "same_pathogen_class", "shared_descriptors")}
            for m in manifest]
    with open(os.path.join(out_dir, "candidates.json"), "w") as fh:
        json.dump({"min_imgs": min_imgs, "n_pairs": len(cand), "pairs": cand}, fh, indent=2)
    with open(os.path.join(out_dir, "pair_manifest.json"), "w") as fh:
        json.dump({"min_imgs": min_imgs, "knn_gate": KNN_GATE,
                   "n_pairs": len(manifest), "pairs": manifest}, fh, indent=2)
    needs = [{"pair_id": m["pair_id"], "crop": m["crop"],
              "member_a": m["member_a"], "member_b": m["member_b"],
              "lookalike_prior": m["lookalike_prior"]}
             for m in manifest if m["needs_web"]]
    with open(os.path.join(out_dir, "needs_web.json"), "w") as fh:
        json.dump({"n": len(needs), "pairs": needs}, fh, indent=2)
    # a flat CSV for eyeballing / spreadsheets
    cols = ["pair_id", "crop", "member_a", "member_b", "n_imgs_total",
            "lookalike_prior", "web_checked", "web_verified", "confirmed",
            "clip_scored", "matched_cross_knn", "clip_lane_hint", "needs_web"]
    with open(os.path.join(out_dir, "pair_manifest.csv"), "w", newline="") as fh:
        wr = csvmod.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        wr.writeheader()
        wr.writerows(manifest)
    return needs


def summarize(manifest):
    n = len(manifest)
    confirmed = [m for m in manifest if m["confirmed"]]
    web_checked = [m for m in manifest if m["web_checked"]]
    needs_web = [m for m in manifest if m["needs_web"]]
    lane = {"image_ambiguous": 0, "image_decisive": 0, None: 0}
    for m in confirmed:
        lane[m["clip_lane_hint"]] += 1
    img_total = sum(m["n_imgs_total"] for m in confirmed)
    print(f"[identify_pairs] candidate pairs: {n}")
    print(f"  web-checked so far: {len(web_checked)}  "
          f"-> CONFIRMED (web-verified, the gate): {len(confirmed)}")
    print(f"  CLIP lane routing of confirmed pairs: "
          f"Lane-B image_ambiguous={lane['image_ambiguous']}, "
          f"Lane-A image_decisive={lane['image_decisive']}, "
          f"unscored(VLM decides)={lane[None]}")
    print(f"  raw image-items across confirmed pairs (both members): {img_total}")
    print(f"  STILL NEEDS WEB CHECK (full-sweep work-list): {len(needs_web)} pairs")
    if web_checked:
        rate = len(confirmed) / len(web_checked)
        proj = int(round(rate * n))
        print(f"  observed web pass-rate {rate:.0%} -> projected confirmed at full "
              f"sweep ≈ {proj} pairs")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=DEFAULT_SOURCE,
                    help="ImageFolder dataset dir (default: GPQA_SOURCE / CyAg)")
    ap.add_argument("--min-imgs", type=int, default=12)
    ap.add_argument("--out-dir", default=PAIRS_DIR)
    args = ap.parse_args()

    manifest = identify(args.source, args.min_imgs)
    write_outputs(manifest, args.min_imgs, args.out_dir)
    summarize(manifest)
    print(f"  wrote: {args.out_dir}/candidates.json, pair_manifest.json, "
          f"pair_manifest.csv, needs_web.json")


if __name__ == "__main__":
    main()
