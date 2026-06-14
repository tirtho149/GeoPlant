#!/usr/bin/env python
"""
Visual flow of how look-alike PAIRS are created (and turned into items).
Renders flow.pdf with matplotlib (no LaTeX).

    python scripts/make_flow_pdf.py --out flow.pdf
"""
from __future__ import annotations
import argparse, json, os, sys, collections

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from geophyto_qa.build import load_rows  # noqa
from geophyto_qa.mine_pairs import mine  # noqa

BLUE = "#dbe7f3"; GREEN = "#d8efdc"; AMBER = "#fbecd0"; GREY = "#ececec"; EDGE = "#33414f"


def counts():
    rows = load_rows(os.path.join(ROOT, "BugWood_Diseases_enriched.csv"))
    cand = len(mine(rows, 12))
    conf = json.load(open(os.path.join(ROOT, "geophyto_qa/lookalike/confirmed_lookalikes.json")))
    nconf = sum(1 for e in conf.values() if e.get("confirmed"))
    items = [json.loads(l) for l in open(os.path.join(ROOT, "geophyto_qa.jsonl")) if l.strip()]
    pwi = len({i["lookalike"]["pair_id"] for i in items})
    return cand, nconf, pwi, len(items)


def box(ax, x, y, w, h, title, body, color, tcolor=EDGE):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.006,rounding_size=0.012",
                                fc=color, ec=EDGE, lw=1.3))
    ax.text(x + w / 2, y + h - 0.018, title, ha="center", va="top", fontsize=9.5,
            weight="bold", color=tcolor)
    if body:
        ax.text(x + w / 2, y + h - 0.046, body, ha="center", va="top", fontsize=7.6, color="#222")


def arrow(ax, x0, y0, x1, y1, label=None):
    ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=15,
                                 lw=1.6, color=EDGE, shrinkA=0, shrinkB=0))
    if label:
        ax.text((x0 + x1) / 2 + 0.02, (y0 + y1) / 2, label, fontsize=7, style="italic", color="#555")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "flow.pdf"))
    a = ap.parse_args()
    cand, nconf, pwi, nit = counts()

    fig = plt.figure(figsize=(8.5, 11))
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    fig.text(0.5, 0.975, "How a look-alike PAIR is created", ha="center", fontsize=16, weight="bold")
    fig.text(0.5, 0.953, "GeoPlant / geophyto_qa  ·  image → look-alike-label diagnosis VQA",
             ha="center", fontsize=9.5, color="#555")

    cx, w = 0.06, 0.60          # main column
    # 0. source
    box(ax, cx, 0.875, w, 0.055, "Bugwood disease table  (BugWood_Diseases_enriched.csv)",
        "host · disease · scientific name · image URL · state", GREY)
    # 1. mine
    box(ax, cx, 0.760, w, 0.075, "1 · MINE PAIRS",
        "within ONE crop, take every pair of its diseases as a\ncandidate look-alike (combinatorial)", BLUE)
    # 2. confirm (web gate + CLIP)
    box(ax, cx, 0.620, w, 0.105, "2 · CONFIRM THE PAIR  (two-level)",
        "WEB GATE: a credible source (extension / .edu / journal)\n"
        "states the two are confused  → quote + URL  (this decides)\n"
        "CLIP: photos of the two classes are visually entangled\n"
        "(cross-kNN)  → attached as evidence", GREEN)
    # 3. graph
    box(ax, cx, 0.505, w, 0.075, "3 · DECISION GRAPH (per pair)",
        "author the ONE decisive VISIBLE sign that tells\nmember A from member B  (+ lay wording, management)", AMBER)
    # 4. vlm
    box(ax, cx, 0.405, w, 0.065, "4 · VLM LABEL (per image)",
        "for each Bugwood photo: is the deciding sign visible?\nclose-up? which organ?", AMBER)
    # 5. build
    box(ax, cx, 0.300, w, 0.070, "5 · BUILD → ITEM (per sign-visible image)",
        "render farmer↔expert dialogue: expert reads the visible\nsign, diagnoses, RULES OUT the look-alike", BLUE)
    # 6. item
    box(ax, cx, 0.175, w, 0.085, "OUTPUT ITEM",
        "image  +  6-turn dialogue  +  CoT (PERCEIVE→READ_SIGN→\nRULE_OUT→CONCLUDE)  +  gold {diagnosis, ruled_out,\nevidence_from_image}", "#e7ddf3")

    # arrows down the column
    xm = cx + w / 2
    for y0, y1 in [(0.875, 0.835), (0.760, 0.725), (0.620, 0.580),
                   (0.505, 0.470), (0.405, 0.370), (0.300, 0.260)]:
        arrow(ax, xm, y0, xm, y1)

    # funnel of real counts (right column)
    fx = 0.72
    ax.add_patch(FancyBboxPatch((fx, 0.300), 0.24, 0.535,
                 boxstyle="round,pad=0.008,rounding_size=0.012", fc="#fafafa", ec=EDGE, lw=1.1))
    ax.text(fx + 0.12, 0.822, "counts", ha="center", fontsize=9, weight="bold")
    funnel = [("candidate pairs", cand, 0.730),
              ("→ confirmed look-alikes", nconf, 0.600),
              ("→ pairs with items", pwi, 0.470),
              ("→ dataset items", nit, 0.350)]
    for label, val, y in funnel:
        ax.text(fx + 0.12, y + 0.030, f"{val:,}", ha="center", fontsize=15, weight="bold", color="#1c4f7c")
        ax.text(fx + 0.12, y + 0.008, label, ha="center", fontsize=7.4, color="#444")

    # worked example strip (bottom)
    ax.add_patch(FancyBboxPatch((0.06, 0.045), 0.88, 0.105,
                 boxstyle="round,pad=0.008,rounding_size=0.012", fc="#fff8e8", ec=EDGE, lw=1.1))
    ax.text(0.5, 0.135, "worked example", ha="center", fontsize=8.5, weight="bold", color="#7a5b00")
    ax.text(0.08, 0.115,
            "crop = cucumber → diseases {anthracnose, downy mildew, gummy stem blight, powdery mildew, ...}\n"
            "candidate pair  =  Anthracnose  ×  Cucurbit Downy Mildew\n"
            "WEB GATE ✓  \"anthracnose ... is easily confused with downy mildew\" (UF/IFAS)   +   CLIP entangled ✓\n"
            "DECISION GRAPH → decisive sign: sunken lesions with salmon-pink ooze (anthracnose) vs angular spots,\n"
            "fuzzy gray-purple underside (downy mildew)   →   each sign-visible photo → one diagnosis item",
            ha="left", va="top", fontsize=7.3, color="#333")

    fig.savefig(a.out)
    print(f"wrote {a.out}  (candidates {cand}, confirmed {nconf}, pairs-with-items {pwi}, items {nit})")


if __name__ == "__main__":
    main()
