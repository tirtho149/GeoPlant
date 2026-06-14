"""
S16 — split-hygiene check.   [CPU]

Asserts no Bugwood image_number appears in more than one split (image-level leakage
inflates "heldout" claims). Reports split sizes and lane x split breakdown. Exits
non-zero if any image leaks across splits, so it can gate a pipeline.

Usage:
  python -m geophyto_qa.audit.check_splits --jsonl geophyto_qa.jsonl
"""
import argparse, json, os, sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", default=os.path.join(ROOT, "geophyto_qa.jsonl"))
    a = ap.parse_args()

    img_splits = defaultdict(set)
    splits = Counter()
    lane_split = Counter()
    n = 0
    with open(a.jsonl) as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line); n += 1
            im = (r.get("image", {}) or {}).get("image_number")
            sp = r.get("split", "?")
            lane = (r.get("lookalike", {}) or {}).get("clip_lane_hint") or r.get("lane", "?")
            splits[sp] += 1
            lane_split[(sp, lane)] += 1
            if im:
                img_splits[im].add(sp)

    leaks = {im: sorted(s) for im, s in img_splits.items() if len(s) > 1}
    print(f"items: {n}  distinct images: {len(img_splits)}")
    print(f"splits: {dict(splits)}")
    print(f"lane x split: {dict(lane_split)}")
    if leaks:
        print(f"\nFAIL: {len(leaks)} images span >1 split (image-level leakage):")
        for im, s in list(leaks.items())[:20]:
            print(f"  {im} -> {s}")
        sys.exit(1)
    print("\nOK: no image spans more than one split.")


if __name__ == "__main__":
    main()
