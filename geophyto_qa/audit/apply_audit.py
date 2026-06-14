"""
S12 — turn prior-audit verdicts into Lane-B corrections.   [CPU]

Reads prior_audit.json and emits a corrections table the rebuild (S15) consumes.
Nothing is dropped silently — every action is logged with its reason.

  agree              keep            (prior justified)
  flip               relabel         (gold should be the distractor; or drop with --drop-flip)
  non_discriminative drop_from_lane_b(geography can't decide; not valid Lane-B material)
  undetermined       flag            (kept, marked low_confidence for review)

Output lane_b_corrections.json maps "host|true|distractor|region" -> action, so the
builder can look up each Lane-B item by its grounding and apply the correction.

Usage:
  python -m geophyto_qa.audit.apply_audit \
      --audit geophyto_qa/audit/prior_audit.json \
      --out   geophyto_qa/audit/lane_b_corrections.json
"""
import argparse, json, os
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ACTION = {
    "agree": "keep",
    "flip": "relabel",
    "non_discriminative": "drop_from_lane_b",
    "undetermined": "flag",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", default=os.path.join(ROOT, "geophyto_qa", "audit", "prior_audit.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "geophyto_qa", "audit", "lane_b_corrections.json"))
    ap.add_argument("--drop-flip", action="store_true",
                    help="drop flipped pairs instead of relabeling gold to the distractor")
    a = ap.parse_args()

    audit = json.load(open(a.audit))
    corrections, counts, items = {}, Counter(), Counter()
    for r in audit["results"]:
        v = r["verdict"]
        action = ACTION[v]
        if v == "flip" and a.drop_flip:
            action = "drop_from_lane_b"
        key = f"{r['host']}|{r['true']}|{r['distractor']}|{r['region']}"
        corrections[key] = {
            "action": action,
            "verdict": v, "why": r["why"], "items": r.get("items", 0),
            "relabel_to": r["distractor"] if action == "relabel" else None,
        }
        counts[action] += 1
        items[action] += r.get("items", 0)

    json.dump({"actions": dict(counts), "items": dict(items), "corrections": corrections},
              open(a.out, "w"), indent=2)
    print("Lane-B corrections:")
    for act in ("keep", "relabel", "drop_from_lane_b", "flag"):
        if counts[act]:
            print(f"  {act:18s}: {counts[act]:4d} combos | {items[act]} items")
    print(f"-> {a.out}")


if __name__ == "__main__":
    main()
