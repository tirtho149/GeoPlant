"""
geophyto_qa.lookalike.verify_pairs
=================================
WEB-FIRST confirmation: the credible web source is the GATE; the image-encoder
confusability is the ROUTER.

ROUTER source = FLAVA bidirectional-entailment confusability (flava_scores.json,
written by geophyto_qa.lookalike.flava_confuse), replacing the old CLIP cross-kNN.
The score lives under the same key (`matched.matched_cross_knn`), so nothing here
changed except where the score comes from. (Pass --clip clip_scores.json to fall
back to the CLIP baseline for an ablation.)

    confirmed   = web_verified (an extension / university / gov / peer-reviewed
                  source states the two are confused)              <- the GATE
    clip_lane_hint  routes a confirmed pair into a dialogue lane   <- the ROUTER
        image_ambiguous : CLIP cross-kNN >= gate  -> visually entangled, the
                          deciding sign tends NOT to separate them in a photo,
                          so geography is load-bearing (Lane B, the novelty).
        image_decisive  : CLIP cross-kNN <  gate  -> CLIP separates them, i.e.
                          the deciding sign is visible, so the image decides
                          (Lane A, the VQA control lane).
        None            : no CLIP score yet -> per-image VLM decides the lane.

Why web-first: the web label is the AUTHORITATIVE definition of "look-alike"
(an agronomist saying the two are confused is ground truth); CLIP cross-kNN is a
noisy proxy that deflates to ~0 when the pair is photographed on different organs
(fruit vs leaf), wrongly rejecting real look-alikes. Gating on CLIP let the weak
signal veto the strong one and discarded ~62% of web-documented look-alikes (the
CLIP-separable ones) that are in fact valid Lane-A material. Here CLIP no longer
vetoes anything — it only labels which lane a web-confirmed pair belongs to.

Each confirmed pair still carries BOTH pieces of evidence (web quote/URL +
CLIP score) so every look-alike claim in GeoPhyto-QA is auditable end to end.

CLI:
  python -m geophyto_qa.lookalike.verify_pairs \
      --clip geophyto_qa/lookalike/clip_scores.json \
      --web  geophyto_qa/lookalike/web_evidence.json \
      --out  geophyto_qa/lookalike/confirmed_lookalikes.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
ROOT = os.path.dirname(PKG)
sys.path.insert(0, ROOT)
from geophyto_qa.disease_norm import build_sci_map, same_organism_drops  # noqa: E402
# CLIP no longer GATES — it ROUTES. The organ-matched cross-kNN threshold now
# only splits web-confirmed pairs into lanes: >= gate -> visually entangled
# (image_ambiguous / Lane B); < gate -> separable (image_decisive / Lane A).
# 0.20 (cf. 0.12 toothless / 0.5 = fully intermixed) is the entanglement cutoff.
KNN_GATE = 0.20


def clip_lane_hint(mk, knn_gate=KNN_GATE):
    """Route a web-confirmed pair into a lane from its organ-matched cross-kNN.
    None when CLIP hasn't scored the pair (per-image VLM then decides the lane)."""
    if mk is None:
        return None
    return "image_ambiguous" if mk >= knn_gate else "image_decisive"


def combine(clip_path, web_path, knn_gate=KNN_GATE, source=None):
    clip = json.load(open(clip_path)).get("scores", {}) if os.path.exists(clip_path) else {}
    web = json.load(open(web_path)) if os.path.exists(web_path) else {}
    pair_ids = set(clip) | set(web)
    out = {}
    for pid in sorted(pair_ids):
        c = clip.get(pid, {})
        w = web.get(pid, {})
        matched = c.get("matched", {}) or {}
        mk = matched.get("matched_cross_knn")
        # CLIP descriptor: entangled vs separable on the ORGAN-MATCHED metric.
        img_entangled = bool(mk is not None and mk >= knn_gate)
        web_ok = bool(w.get("verified"))
        out[pid] = {
            # WEB IS THE GATE.
            "confirmed": web_ok,
            "web_verified": web_ok,
            # CLIP IS THE ROUTER (descriptor + lane hint, never a veto).
            "image_confusable": img_entangled,
            "clip_lane_hint": clip_lane_hint(mk, knn_gate),
            "clip_scored": mk is not None,
            "clip": {"matched_cross_knn": mk,
                     "whole_image_cross_knn": c.get("whole_image_cross_knn"),
                     "shared_buckets": matched.get("shared_buckets"),
                     "matched_support": matched.get("matched_support"),
                     "n_a": c.get("n_a"), "n_b": c.get("n_b"),
                     "knn_gate": knn_gate},
            "web": {k: w.get(k) for k in
                    ("quote", "source_url", "source_title", "source_type", "claim")
                    if k in w},
            "crop": w.get("crop"),
            "member_a": w.get("member_a"), "member_b": w.get("member_b"),
        }
    # label hygiene: drop same-organism (disease-vs-itself) confirmed pairs.
    confirmed = {p: d for p, d in out.items() if d["confirmed"]}
    sci = build_sci_map(source)
    for pid in same_organism_drops(confirmed, sci):
        out[pid]["confirmed"] = False
        out[pid]["dropped_reason"] = "same organism (synonym)"
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip", default=os.path.join(HERE, "flava_scores.json"),
                    help="image-encoder confusability scores (default: FLAVA bidirectional; "
                         "pass clip_scores.json for the CLIP baseline)")
    ap.add_argument("--web", default=os.path.join(HERE, "web_evidence.json"))
    ap.add_argument("--out", default=os.path.join(HERE, "confirmed_lookalikes.json"))
    args = ap.parse_args()

    res = combine(args.clip, args.web)
    with open(args.out, "w") as fh:
        json.dump(res, fh, indent=2)

    confirmed = [p for p, r in res.items() if r["confirmed"]]
    pending_web = [p for p, r in res.items() if not r["web_verified"] and "verified"
                   not in res[p].get("web", {})]
    # lane routing among confirmed (web-gated) pairs
    lane = {"image_ambiguous": 0, "image_decisive": 0, None: 0}
    for p in confirmed:
        lane[res[p].get("clip_lane_hint")] += 1
    print(f"[WEB-GATE / CLIP-ROUTER] confirmed look-alikes (web-verified): "
          f"{len(confirmed)}/{len(res)} -> {args.out}")
    print(f"  lane routing of confirmed pairs: "
          f"Lane-B image_ambiguous={lane['image_ambiguous']}, "
          f"Lane-A image_decisive={lane['image_decisive']}, "
          f"unscored(VLM-decides)={lane[None]}")
    print(f"  not yet web-verified: {len(res) - len(confirmed)} "
          f"(of which no web evidence at all: {len(pending_web)})")
    for p, r in res.items():
        tag = "CONFIRMED" if r["confirmed"] else "web✗"
        hint = r.get("clip_lane_hint") or "vlm"
        mk = r["clip"].get("matched_cross_knn")
        print(f"  {tag:10s} lane={hint:16s} knn={mk if mk is not None else '-'}  {p}")


if __name__ == "__main__":
    main()
