"""Build per-crop part_index.md — Organ Part Index.

Adapted from tirtho149/SAGE open_agentic/build_part_index.py. The original scans
a <Class>/<part>/ folder tree; Bugwood has no such tree (its Descriptor column is
organ-agnostic for ~70% of images), so here the per-image anatomical part comes
from the VLM labeling pass (geophyto_qa/lookalike/vlm_labels.json), and a class
is listed under a part when >= --min-imgs of its images show that part.

Output format matches SAGE's part_index.md exactly (plain headers, no '##' / '-'):

    # Organ Part Index — <Crop>

    Use this to narrow candidates based on the plant part visible in the test image.

    leaf (N classes)
    Class1
    Class2

    fruit (M classes)
    ...

Usage:
    python -m geophyto_qa.anatomy.build_part_index \
        --labels geophyto_qa/lookalike/vlm_labels.json \
        --out-dir geophyto_qa/anatomy/part_index --min-imgs 2
"""
from __future__ import annotations

import argparse
import collections
import json
import os

# SAGE PARTS extended with fruit/flower for the fruit/vegetable crops here
# (legume pod/seed retained). Order controls the output section order.
PARTS = ("leaf", "stem", "root", "fruit", "flower", "pod", "seed", "whole_plant")
# normalize free-form VLM part strings into the taxonomy.
_PART_ALIASES = {
    "leaves": "leaf", "foliage": "leaf", "leaflet": "leaf",
    "stems": "stem", "vine": "stem", "twig": "stem", "cane": "stem", "branch": "stem",
    "roots": "root", "tuber": "root", "crown": "root", "storage root": "root",
    "fruits": "fruit", "berry": "fruit", "head": "fruit",
    "flowers": "flower", "blossom": "flower",
    "pods": "pod", "seeds": "seed", "kernel": "seed",
    "whole plant": "whole_plant", "plant": "whole_plant", "seedling": "whole_plant",
}


def norm_part(p: str) -> str | None:
    p = (p or "").strip().lower()
    if p in PARTS:
        return p
    return _PART_ALIASES.get(p)


def build(labels_path: str, out_dir: str, min_imgs: int = 2, exclude=None):
    exclude = exclude or set()
    labels = json.load(open(labels_path))
    # (crop, part) -> Counter(class -> n images)
    counts = collections.defaultdict(lambda: collections.Counter())
    for rec in labels.values():
        crop, dis = rec.get("crop"), rec.get("disease")
        part = norm_part(rec.get("anatomical_part"))
        if not (crop and dis and part) or dis in exclude:
            continue
        counts[(crop, part)][dis] += 1

    crops = sorted({c for (c, _) in counts})
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for crop in crops:
        lines = [f"# Organ Part Index — {crop}", "",
                 "Use this to narrow candidates based on the plant part visible in the test image.",
                 ""]
        any_part = False
        for part in PARTS:
            cls = sorted(c for c, n in counts.get((crop, part), {}).items() if n >= min_imgs)
            if not cls:
                continue
            any_part = True
            lines.append(f"{part} ({len(cls)} classes)")
            lines.extend(cls)
            lines.append("")
        if not any_part:
            continue
        path = os.path.join(out_dir, f"{crop.replace(' ', '_')}.md")
        open(path, "w").write("\n".join(lines))
        written.append((crop, path))
    return written


def main():
    HERE = os.path.dirname(os.path.abspath(__file__))
    PKG = os.path.dirname(HERE)
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", default=os.path.join(PKG, "lookalike", "vlm_labels.json"))
    ap.add_argument("--out-dir", default=os.path.join(HERE, "part_index"))
    ap.add_argument("--min-imgs", type=int, default=2)
    ap.add_argument("--exclude", default="")
    args = ap.parse_args()
    exclude = {c.strip() for c in args.exclude.split(",") if c.strip()}
    written = build(args.labels, args.out_dir, args.min_imgs, exclude)
    print(f"wrote {len(written)} part_index.md files -> {args.out_dir}")
    for crop, path in written:
        print(f"  {crop}: {path}")


if __name__ == "__main__":
    main()
