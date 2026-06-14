#!/usr/bin/env python3
"""Render ONE GeoPhyto-CoT VQA item to a one-page PDF (image + plant-only CoT)."""
import json, os, sys, textwrap
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from PIL import Image

ITEM = sys.argv[1] if len(sys.argv) > 1 else "/tmp/sample_item.json"
IMG  = sys.argv[2] if len(sys.argv) > 2 else "/tmp/1563309.jpg"
OUT  = sys.argv[3] if len(sys.argv) > 3 else os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "geo_vqa_sample.pdf")

it = json.load(open(ITEM))
lab = it["labels"]; img_meta = it["image"]

fig = plt.figure(figsize=(8.5, 11))
fig.subplots_adjust(left=0.07, right=0.93, top=0.95, bottom=0.04)

# ---- title ----
fig.text(0.5, 0.965, "GeoPhyto-CoT — Ecological Geolocation VQA (sample)",
         ha="center", fontsize=15, weight="bold")
fig.text(0.5, 0.945, f"item {it['id']}  ·  type={it['question_type']}  ·  "
         f"split={it['split']}  ·  source={it['reasoning_source']}",
         ha="center", fontsize=8.5, color="#555")

# ---- image (top-left) ----
ax = fig.add_axes([0.07, 0.66, 0.40, 0.26])
ax.imshow(Image.open(IMG)); ax.axis("off")
ax.set_title(f"Bugwood #{img_meta['image_number']}  ({img_meta.get('descriptor','')})",
             fontsize=8)

# ---- labels / answer (top-right) ----
def wrap(s, w): return "\n".join(textwrap.wrap(s, w))
meta = (f"INPUT: the image only (a symptom close-up).\n"
        f"TASK: predict where it was captured.\n\n"
        f"Host: {lab['host_common']}\n      ({lab['host_sci']})\n"
        f"Disease: {lab['disease']}\n"
        f"Pathogen: {lab.get('pathogen_sci','')}\n\n"
        f"GOLD geo tag: {it['answer']}\n"
        f"  tier: {it['answer_tier']}\n"
        f"  region: {it['answer_tiers']['region']}\n"
        f"  Köppen: {it['answer_tiers']['koppen_zone']}\n"
        f"reasoning-capable: {it['reasoning_capable']}")
fig.text(0.50, 0.915, meta, fontsize=8.4, va="top", family="DejaVu Sans",
         bbox=dict(boxstyle="round", fc="#f3f6fb", ec="#bcd"))

fig.text(0.07, 0.625, "Question:", fontsize=9.5, weight="bold")
fig.text(0.07, 0.61, wrap(it["question"], 110), fontsize=8.3, va="top")

# ---- CoT ----
y = 0.55
fig.text(0.07, y, "Plant-portion-driven chain-of-thought  (no background/scene cues):",
         fontsize=10, weight="bold"); y -= 0.022
COLOR = {"PERCEIVE": "#1b7837", "IDENTIFY_HOST": "#2166ac", "DIAGNOSE_AGENT": "#762a83",
         "GEO_PRIOR": "#b35806", "NARROW": "#01665e", "CONCLUDE": "#a50026"}
for s in it["cot"]:
    head = f"[{s['step']}]  ({s['cites']})"
    fig.text(0.08, y, head, fontsize=8.2, weight="bold", color=COLOR.get(s["step"], "#000"))
    y -= 0.018
    body = wrap(s["text"], 116)
    fig.text(0.09, y, body, fontsize=8.0, va="top")
    y -= 0.0145 * (body.count("\n") + 1) + 0.006

# ---- plant-only visual evidence from the swarm ----
ev = it.get("visual_evidence") or []
if ev and y > 0.18:
    y -= 0.005
    fig.text(0.07, y, f"PRESAGE plantswarm visual evidence (plant-only, {len(ev)} obs):",
             fontsize=9, weight="bold"); y -= 0.02
    for e in ev[:7]:
        line = f"• [{e['organ']}/{e['field']}] {e['observation']}"
        line = wrap(line, 118)
        fig.text(0.08, y, line, fontsize=7.4, va="top", color="#333")
        y -= 0.013 * (line.count("\n") + 1) + 0.003

fig.text(0.5, 0.018, f"image: {img_meta['url']}  ·  {img_meta.get('attribution','')}",
         ha="center", fontsize=6.3, color="#888")

with PdfPages(OUT) as pdf:
    pdf.savefig(fig)
plt.close(fig)
print("wrote", OUT, os.path.getsize(OUT), "bytes")
