#!/usr/bin/env python
"""
Manual-check review PDF for GeoPhyto-QA — ONE LOOK-ALIKE PAIR per page:
the two confusable diseases shown SIDE BY SIDE (member A vs member B photo) +
the web evidence that they are confused + one example dialogue/CoT/gold from the
pair. For eyeballing whether the pair really looks alike and the reasoning holds.

    python scripts/make_review_pdf.py --out geophyto_qa_review10.pdf --n 10
"""
from __future__ import annotations
import argparse, io, json, os, sys, textwrap, collections

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from geophyto_qa.lookalike.clip_confuse import _fetch  # noqa
from geophyto_qa.build import load_rows, mine  # noqa
from geophyto_qa.disease_norm import clean_display  # noqa

IMGDIR = os.path.join(ROOT, "figures", "img_cache")
CSV = os.path.join(ROOT, "BugWood_Diseases_enriched.csv")


def get_image(imgnum):
    os.makedirs(IMGDIR, exist_ok=True)
    path = os.path.join(IMGDIR, f"{imgnum}.jpg")
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return Image.open(path).convert("RGB")
    raw = _fetch(imgnum, timeout=20)
    if raw and len(raw) > 1000:
        open(path, "wb").write(raw)
        return Image.open(io.BytesIO(raw)).convert("RGB")
    return None


def show(ax, it, caption_lab):
    ax.axis("off")
    im = get_image((it.get("image", {}) or {}).get("image_number", "")) if it else None
    if im is not None:
        ax.imshow(im)
    else:
        ax.text(0.5, 0.5, "(image\nunavailable)", ha="center", va="center", fontsize=9)
    g = (it or {}).get("grounding", {})
    ax.set_title(f"{caption_lab}\n{g.get('host','')}/{g.get('anatomical_part','')} @ {g.get('state','')}",
                 fontsize=8)


def wrap(label, text, w=108):
    return f"{label}{textwrap.fill(text, w, subsequent_indent='        ')}"


def page(pdf, pair_id, rep, img_true, img_dist, idx, total):
    fig = plt.figure(figsize=(8.5, 11))
    lk = rep["lookalike"]; gold = rep["gold"]; ev = lk.get("evidence") or {}
    true_lab, dist_lab = lk.get("true"), lk.get("distractor")

    fig.text(0.5, 0.978, f"GeoPhyto-QA look-alike review  ·  pair {idx}/{total}",
             ha="center", fontsize=13, weight="bold")
    fig.text(0.5, 0.960, f"{true_lab}   vs   {dist_lab}   ·   crop: {lk.get('crop')}",
             ha="center", fontsize=10, weight="bold")

    # two member images side by side
    axL = fig.add_axes([0.05, 0.62, 0.43, 0.30]); show(axL, img_true, f"A · {true_lab}")
    axR = fig.add_axes([0.52, 0.62, 0.43, 0.30]); show(axR, img_dist, f"B · {dist_lab}")

    lines = []
    lines.append(wrap("LOOK-ALIKE EVIDENCE (web): ", ev.get("web_quote") or "(none)"))
    lines.append(f"   source: {(ev.get('web_source_title') or '')[:80]}")
    lines.append(f"   CLIP lane hint: {ev.get('clip_lane_hint')}   (clip={ev.get('clip',{})})")
    lines.append("")
    lines.append(f"EXAMPLE DIALOGUE  (item {rep['item_id']}, split={rep.get('split')})")
    for t in rep["dialogue"]:
        tag = "(img)" if t.get("has_image") else "     "
        lines.append(wrap(f"  [{t['turn']}]{tag} {t['speaker']}: ", t["text"]))
    lines.append("")
    for s in rep["cot"]:
        lines.append(wrap(f"  CoT {s['step']}: ", s["text"]))
    lines.append("")
    lines.append(f"GOLD: dx={gold.get('diagnosis')}  ruled_out={gold.get('ruled_out')}  "
                 f"answerable_from_image={gold.get('answerable_from_image')}")
    lines.append(wrap("  evidence_from_image: ", gold.get("evidence_from_image") or ""))

    fig.text(0.05, 0.57, "\n".join(lines), fontsize=6.8, family="monospace",
             va="top", linespacing=1.35)
    pdf.savefig(fig); plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", default=os.path.join(ROOT, "geophyto_qa.jsonl"))
    ap.add_argument("--out", default=os.path.join(ROOT, "geophyto_qa_review10.pdf"))
    ap.add_argument("--n", type=int, default=10)
    a = ap.parse_args()

    items = [json.loads(l) for l in open(a.jsonl) if l.strip()]
    by_pair = collections.defaultdict(list)
    for it in items:
        by_pair[it["lookalike"].get("pair_id")].append(it)

    # source CSV: images per (crop, disease) so we can show the distractor photo
    # even when no dataset item exists for that member.
    rows = load_rows(CSV)
    by_cd = collections.defaultdict(list)
    for r in rows:
        by_cd[(r["crop"], r["disease"])].append(r)
    pairs = {p["pair_id"]: p for p in mine(rows, 12)}

    def member_img(pid, lab):
        # 1) a real dataset item whose true == lab
        for it in by_pair[pid]:
            if it["lookalike"].get("true") == lab:
                return it
        # 2) fall back to a raw Bugwood image of that member from the CSV
        p = pairs.get(pid)
        if p:
            for m in ("member_a", "member_b"):
                if clean_display(p[m]["disease"]) == lab:
                    rws = by_cd.get((p["crop"], p[m]["disease"]), [])
                    if rws:
                        r = rws[0]
                        return {"image": {"image_number": r["img"]},
                                "grounding": {"host": p["crop"], "anatomical_part": "",
                                              "state": r.get("state", "")}}
        return None

    chosen = [pid for pid in by_pair if pid][:a.n]

    with PdfPages(a.out) as pdf:
        for i, pid in enumerate(chosen, 1):
            rep = by_pair[pid][0]
            img_true = member_img(pid, rep["lookalike"]["true"]) or rep
            img_dist = member_img(pid, rep["lookalike"]["distractor"])
            page(pdf, pid, rep, img_true, img_dist, i, len(chosen))
    print(f"wrote {len(chosen)}-pair review PDF -> {a.out}  "
          f"({len(by_pair)} confirmed look-alike pairs total)")


if __name__ == "__main__":
    main()
