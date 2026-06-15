"""
geophyto_qa.mine_pairs
======================
Mine candidate within-crop look-alike disease pairs from the geo-enriched
Bugwood CSV. This is the *work-list* for the full sweep: every pair gets an
LLM-authored discriminator graph (graphgen) and is then either kept (confusable)
or dropped.

A pair (crop, disease_a, disease_b) is a candidate when both members carry at
least ``--min-imgs`` images on the same crop, so each yields enough VQA items
and the geo-oracle has signal. We DO NOT decide confusability here — that is the
LLM's job — but we attach cheap features (shared descriptors, same pathogen
class, geographic overlap) that bias the generator and let us sort the sweep so
the most likely look-alikes are authored first.

CLI:
    python -m geophyto_qa.mine_pairs --min-imgs 12 --out geophyto_qa/pairs/candidates.json
"""
from __future__ import annotations

import argparse
import collections
import itertools
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from geophyto_qa.data_source import load_rows, DEFAULT_SOURCE  # noqa: E402
from geophyto_qa.regions import pathogen_class, region_of    # noqa: E402  (taxonomy + geo metadata)
from geophyto_qa.quality.label_gate import filter_rows       # noqa: E402  (step-0 gate; no-op if absent)


def pair_key(crop: str, a: str, b: str) -> str:
    """Stable id independent of member order; member_a is alphabetically first."""
    a, b = sorted((a, b))
    slug = lambda s: "".join(c.lower() if c.isalnum() else "-" for c in s).strip("-")
    return f"{slug(crop)}__{slug(a)}__{slug(b)}", a, b


def mine(rows, min_imgs: int = 12):
    by_crop_dis = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in rows:
        by_crop_dis[r["crop"]][r["disease"]].append(r)

    pairs = []
    for crop, dz in by_crop_dis.items():
        elig = [d for d, rs in dz.items() if len(rs) >= min_imgs]
        for a, b in itertools.combinations(sorted(elig), 2):
            ra, rb = dz[a], dz[b]
            pid, ma, mb = pair_key(crop, a, b)
            # order member rows to match ma/mb
            rows_a, rows_b = (ra, rb) if ma == a else (rb, ra)
            desc_a = collections.Counter(x["descriptor"] for x in rows_a)
            desc_b = collections.Counter(x["descriptor"] for x in rows_b)
            shared_desc = sorted(set(desc_a) & set(desc_b))
            states_a = {x["state"] for x in rows_a}
            states_b = {x["state"] for x in rows_b}
            pc_a = pathogen_class(rows_a[0]["path_sci"] or rows_a[0]["path_common"])
            pc_b = pathogen_class(rows_b[0]["path_sci"] or rows_b[0]["path_common"])
            # cheap look-alike prior: shared organ/descriptor + same pathogen class
            # + geographic co-occurrence raise the odds of genuine confusion.
            score = (len(shared_desc)
                     + (2 if pc_a == pc_b else 0)
                     + len(states_a & states_b) / 10.0)
            pairs.append({
                "pair_id": pid,
                "crop": crop,
                "member_a": {"disease": ma, "n_imgs": len(rows_a),
                             "pathogen_class": pc_a,
                             "path_sci": rows_a[0]["path_sci"],
                             "descriptors": desc_a.most_common(4)},
                "member_b": {"disease": mb, "n_imgs": len(rows_b),
                             "pathogen_class": pc_b,
                             "path_sci": rows_b[0]["path_sci"],
                             "descriptors": desc_b.most_common(4)},
                "shared_descriptors": shared_desc,
                "same_pathogen_class": pc_a == pc_b,
                "shared_states": sorted(states_a & states_b),
                "shared_regions": sorted({region_of(s) for s in (states_a & states_b) if region_of(s)}),
                "lookalike_prior": round(score, 3),
            })
    pairs.sort(key=lambda p: p["lookalike_prior"], reverse=True)
    return pairs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=DEFAULT_SOURCE,
                    help="ImageFolder dataset dir (default: GPQA_SOURCE / CyAg)")
    ap.add_argument("--min-imgs", type=int, default=12)
    ap.add_argument("--out", default=os.path.join(HERE, "pairs", "candidates.json"))
    args = ap.parse_args()

    rows, gate = filter_rows(load_rows(args.source))
    if gate.get("applied"):
        print(f"[label-gate / step 0] {gate}")
    pairs = mine(rows, args.min_imgs)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump({"min_imgs": args.min_imgs, "n_pairs": len(pairs), "pairs": pairs}, fh, indent=2)

    crops = len({p["crop"] for p in pairs})
    print(f"mined {len(pairs)} candidate pairs across {crops} crops "
          f"(min_imgs={args.min_imgs}) -> {args.out}")
    print("top look-alike candidates:")
    for p in pairs[:12]:
        print(f"  [{p['lookalike_prior']:5.1f}] {p['crop']}: "
              f"{p['member_a']['disease']} vs {p['member_b']['disease']} "
              f"(shared: {', '.join(p['shared_descriptors']) or '-'})")


if __name__ == "__main__":
    main()
