#!/usr/bin/env python
"""
Render a showcase PDF for GeoPhyto-QA: overview + pipeline figure + the
two-level-confirmed look-alike pairs (with web evidence) + a full sample item.

    python scripts/make_qa_pdf.py --out geophyto_qa_sample.pdf
"""
from __future__ import annotations
import argparse, json, os, random, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from geophyto_qa.build import load_confirmed          # noqa
from geophyto_qa.lookalike.clip_confuse import load_class_images, _fetch  # noqa

LK = os.path.join(ROOT, "geophyto_qa", "lookalike")
IMGDIR = os.path.join(ROOT, "figures", "img_cache")
DATASET = os.path.join(ROOT, "geophyto_qa.jsonl")
PREF_BUCKETS = ["symptom", "leaf", "sign", "foliage", "fruit", "stem", "whole"]


def download_one(imgnums):
    """Return a local jpg path for the first imgnum that fetches, else None."""
    os.makedirs(IMGDIR, exist_ok=True)
    for n in imgnums:
        path = os.path.join(IMGDIR, f"{n}.jpg")
        if os.path.exists(path) and os.path.getsize(path) > 1000:
            return path
        raw = _fetch(n, timeout=15)
        if raw and len(raw) > 1000:
            open(path, "wb").write(raw)
            return path
    return None


def pick_pair_images(verified, n_target=12):
    """For each confirmed pair, pick one image per member from a SHARED organ
    bucket (so the two photos are genuinely comparable) and download them."""
    class_imgs = load_class_images(os.path.join(ROOT, "BugWood_Diseases_enriched.csv"), None)
    gallery = []
    for p, d in verified:
        crop, a, b = d["crop"], d["member_a"], d["member_b"]
        A = class_imgs.get((crop, a), []); B = class_imgs.get((crop, b), [])
        ba = {}; bb = {}
        for nimg, org in A: ba.setdefault(org, []).append(nimg)
        for nimg, org in B: bb.setdefault(org, []).append(nimg)
        shared = [bk for bk in PREF_BUCKETS if bk in ba and bk in bb]
        shared += [bk for bk in (set(ba) & set(bb)) if bk not in shared]
        pa = pb = None; used = None
        for bk in shared:
            pa = download_one(sorted(ba[bk])[:5]); pb = download_one(sorted(bb[bk])[:5])
            if pa and pb:
                used = bk; break
        if pa and pb:
            gallery.append({"crop": crop, "a": a, "b": b, "imgA": pa, "imgB": pb,
                            "bucket": used, "knn": d["clip"].get("matched_cross_knn"),
                            "quote": d["web"].get("quote", ""),
                            "src": d["web"].get("source_title", ""),
                            "url": d["web"].get("source_url", "")})
        if len(gallery) >= n_target:
            break
    return gallery


def esc(s):
    s = str(s or "")
    for a, b in [("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"), ("$", r"\$"),
                 ("#", r"\#"), ("_", r"\_"), ("{", r"\{"), ("}", r"\}"),
                 ("~", r"\textasciitilde{}"), ("^", r"\textasciicircum{}")]:
        s = s.replace(a, b)
    # unicode the latest dialogues emit -> LaTeX-safe equivalents
    for a, b in [("—", "---"), ("–", "--"), ("→", r"$\rightarrow$"),
                 ("‘", "`"), ("’", "'"), ("“", "``"), ("”", "''"),
                 ("…", r"\ldots{}"), ("×", r"$\times$"), ("·", r"$\cdot$"),
                 ("≥", r"$\geq$"), ("≤", r"$\leq$"), ("°", r"$^\circ$")]:
        s = s.replace(a, b)
    return s


def load_dataset():
    """Read the actual latest build (geophyto_qa.jsonl) — not a re-render."""
    if not os.path.exists(DATASET):
        return []
    return [json.loads(l) for l in open(DATASET) if l.strip()]


def dataset_stats(items):
    import collections
    return {
        "n": len(items),
        "lanes": dict(collections.Counter(i["lane"] for i in items)),
        "splits": dict(collections.Counter(i["split"] for i in items)),
        "pairs": len({i["lookalike"]["pair_id"] for i in items}),
        "controls": sum(1 for i in items if i["counterfactual"].get("control")),
    }


def sample_items(items):
    """One real item per lane (prefer the cucumber anthracnose/downy pair so the
    two lanes are directly comparable), to showcase the two-lane design."""
    out = {}
    pref = "cucumber__anthracnose__cucurbit-downy-mildew"
    for lane in ("image_decisive", "image_ambiguous"):
        cand = [i for i in items if i["lane"] == lane]
        pick = next((i for i in cand if i["lookalike"]["pair_id"] == pref), None)
        out[lane] = pick or (cand[0] if cand else None)
    return out


def build_tex(out_pdf):
    conf = load_confirmed()
    verified = [(p, d) for p, d in conf.items() if d["confirmed"]]
    verified.sort(key=lambda x: (x[1]["crop"], -(x[1]["clip"].get("matched_cross_knn") or 0)))
    items = load_dataset()
    stats = dataset_stats(items)
    samples = sample_items(items)

    L = []
    L.append(r"\documentclass[11pt]{article}")
    L.append(r"\usepackage[utf8]{inputenc}\usepackage[T1]{fontenc}")
    L.append(r"\usepackage[margin=0.9in]{geometry}\usepackage{graphicx}\usepackage{longtable}")
    L.append(r"\usepackage{xcolor}\usepackage{enumitem}\usepackage{hyperref}")
    L.append(r"\hypersetup{colorlinks=true,urlcolor=blue!60!black}")
    L.append(r"\definecolor{lav}{RGB}{205,205,244}\definecolor{grn}{RGB}{200,230,201}")
    L.append(r"\setlength{\parindent}{0pt}\setlength{\parskip}{4pt}")
    L.append(r"\begin{document}")
    L.append(r"\begin{center}{\LARGE\bfseries GeoPhyto-QA}\\[2pt]"
             r"{\large Geography-aware look-alike diagnosis VQA from Bugwood imagery}\\[4pt]"
             r"\small Two-level (CLIP image $\wedge$ web-verified) look-alike confirmation \,$\cdot$\, "
             r"decision-graph CoT \,$\cdot$\, farmer--expert dialogue\end{center}")
    L.append(r"\vspace{4pt}\hrule\vspace{6pt}")

    # overview
    L.append(r"\textbf{What this is.} Each item is a multi-turn, image-grounded farmer$\leftrightarrow$"
             r"agricultural-expert dialogue where the expert reasons through a \emph{look-alike decision "
             r"graph} to tell apart two confusable diseases on the same crop, and the reasoning is "
             r"\emph{geography-aware} (region/season/local disease pressure from a contributor-de-biased "
             r"oracle drive the answer). A pair becomes a look-alike only if it is BOTH visually entangled "
             r"(CLIP, organ-matched) AND documented as confused by a credible web source.")

    # latest-build stats (read straight from geophyto_qa.jsonl)
    if items:
        lanes = stats["lanes"]
        sp = stats["splits"]
        L.append(r"\vspace{2pt}\textbf{Latest build.} \textbf{%d} dialogue items over \textbf{%d} "
                 r"confirmed look-alike pairs. Two reasoning lanes: \textbf{%d} \emph{image-decisive} "
                 r"(Lane A --- the deciding sign is visible, so the answer is read from the photo and "
                 r"geography is a swap \emph{control}) and \textbf{%d} \emph{image-ambiguous} "
                 r"(Lane B --- the sign is absent, so a contributor-de-biased regional prior breaks the "
                 r"tie and the location swap is \emph{expected to flip} the answer). %d counterfactual "
                 r"controls. Splits: %s." % (
                     stats["n"], stats["pairs"],
                     lanes.get("image_decisive", 0), lanes.get("image_ambiguous", 0),
                     stats["controls"],
                     esc(", ".join(f"{k} {v}" for k, v in sorted(sp.items())))))

    # figure
    fig = os.path.join(ROOT, "figures", "geophyto_qa_pipeline.png")
    if os.path.exists(fig):
        L.append(r"\begin{center}\includegraphics[width=\textwidth]{%s}\end{center}" % fig)
        L.append(r"\begin{center}\small\textit{Pipeline: (a) two-level look-alike verification; "
                 r"(b) geography-aware dialogue synthesis.}\end{center}")

    # confirmed pairs table
    L.append(r"\vspace{2pt}\textbf{\large Confirmed look-alike pairs (image $\wedge$ web): %d}" % len(verified))
    L.append(r"\\[2pt]\small Each pair passed CLIP organ-matched cross-kNN entanglement \emph{and} carries a "
             r"verbatim quote from a credible source. (Sweep in progress; count grows.)")
    L.append(r"{\footnotesize")
    L.append(r"\begin{longtable}{p{2.4cm}p{6.6cm}cp{4.0cm}}")
    L.append(r"\textbf{Crop} & \textbf{Look-alike pair} & \textbf{kNN} & \textbf{Source} \\\hline\endhead")
    for p, d in verified:
        knn = d["clip"].get("matched_cross_knn")
        src = d["web"].get("source_title", "") or ""
        src = src.split("(")[0][:42]
        L.append(r"%s & %s \emph{vs} %s & %s & %s \\" % (
            esc(d["crop"]), esc(d["member_a"]), esc(d["member_b"]),
            f"{knn:.2f}" if knn is not None else "--", esc(src)))
    L.append(r"\end{longtable}}")

    # evidence samples
    L.append(r"\vspace{2pt}\textbf{\large Web evidence (verbatim)}")
    picks = [p for p in [
        "juniper__kabatina-blight__phomopsis-cankers-and-twig-blights",
        "tomato__early-blight__septoria-leaf-spot",
        "wheat__barley-yellow-dwarf-virus__wheat-streak-mosaic-virus",
        "cucumber__anthracnose__corynespora-leaf-spot",
        "wheat__stripe-rust__wheat-leaf-rust",
    ] if p in conf and conf[p]["confirmed"]]
    L.append(r"\begin{itemize}[leftmargin=1.2em,itemsep=3pt]")
    for p in picks:
        d = conf[p]
        L.append(r"\item \textbf{%s: %s vs %s} --- ``\emph{%s}'' \\ \footnotesize\url{%s}" % (
            esc(d["crop"]), esc(d["member_a"]), esc(d["member_b"]),
            esc(d["web"].get("quote", "")[:230]), d["web"].get("source_url", "")))
    L.append(r"\end{itemize}")

    # look-alike image gallery
    gallery = pick_pair_images(verified, n_target=12)
    if gallery:
        L.append(r"\newpage\textbf{\large Look-alike image pairs (%d)}\\[2pt]" % len(gallery))
        L.append(r"\small Real Bugwood photos of each member, drawn from a shared organ/presentation bucket "
                 r"so the two are genuinely comparable. Left = member A, right = member B.\par\vspace{4pt}")
        for j, gp in enumerate(gallery):
            knn = gp["knn"]
            L.append(r"\begin{center}")
            L.append(r"\begin{tabular}{cc}")
            L.append(r"\includegraphics[width=6.4cm,height=4.3cm,keepaspectratio]{%s} & "
                     r"\includegraphics[width=6.4cm,height=4.3cm,keepaspectratio]{%s} \\" % (gp["imgA"], gp["imgB"]))
            L.append(r"{\footnotesize\textbf{A: %s}} & {\footnotesize\textbf{B: %s}} \\" % (
                esc(gp["a"]), esc(gp["b"])))
            L.append(r"\end{tabular}\\[1pt]")
            L.append(r"{\footnotesize\textbf{%s} \,$\cdot$\, CLIP kNN $=%s$, bucket=%s \,$\cdot$\, "
                     r"``\emph{%s}''}" % (
                         esc(gp["crop"]), f"{knn:.2f}" if knn is not None else "--",
                         esc(gp["bucket"]), esc(gp["quote"][:150])))
            L.append(r"\end{center}\vspace{2pt}")
            if j % 3 == 2:
                L.append(r"\newpage")

    # sample items — one real record per lane, straight from geophyto_qa.jsonl
    LANE_TITLE = {"image_decisive": "Lane A --- image-decisive (sign visible)",
                  "image_ambiguous": "Lane B --- image-ambiguous (geography breaks the tie)"}
    for li, lane in enumerate(("image_decisive", "image_ambiguous")):
        it = samples.get(lane)
        if not it:
            continue
        L.append(r"\newpage" if li == 0 else r"\vspace{8pt}\hrule\vspace{6pt}")
        if li == 0:
            L.append(r"\textbf{\large Sample items (real records, both lanes)}\\[2pt]")
        g = it["gold"]
        L.append(r"\textbf{%s}\\[2pt]" % LANE_TITLE[lane])
        L.append(r"\colorbox{lav}{\parbox{\dimexpr\textwidth-2\fboxsep}{\textbf{%s} \hfill split: %s\\"
                 r"\textbf{%s} \emph{vs} %s \quad @ %s (%s) \,$\cdot$\, part: %s}}" % (
                     esc(it["item_id"]), esc(it["split"]), esc(it["lookalike"]["true"]),
                     esc(it["lookalike"]["distractor"]), esc(it["grounding"]["state"]),
                     esc(it["grounding"]["region"]), esc(it["grounding"].get("anatomical_part", ""))))
        L.append(r"\vspace{4pt}\textbf{Dialogue}")
        L.append(r"\begin{itemize}[leftmargin=1.1em,itemsep=2pt,label={}]")
        for t in it["dialogue"]:
            who = "Farmer" if t["speaker"] == "farmer" else "Expert"
            img = r"\,\textcolor{grn}{[image]}" if t["has_image"] else ""
            L.append(r"\item \textbf{[%s] %s:}%s %s" % (esc(t["turn"]), who, img, esc(t["text"])))
        L.append(r"\end{itemize}")
        L.append(r"\textbf{Decision-graph CoT}")
        L.append(r"\begin{itemize}[leftmargin=1.1em,itemsep=1pt]")
        for s in it["cot"]:
            cite = s.get("cites", "")
            L.append(r"\item \textbf{%s} {\footnotesize\textit{(%s)}} --- %s" % (
                esc(s["step"]), esc(cite), esc(s["text"])))
        L.append(r"\end{itemize}")
        decided = g.get("evidence_from_image") or g.get("confirm_action") or g.get("decided_by", "")
        L.append(r"\textbf{Gold:} dx = %s; ruled out %s; geography\_used = %s; "
                 r"answerable\_from\_image = %s.\\" % (
                     esc(g["diagnosis"]), esc(g["ruled_out"]),
                     esc(g.get("geography_used")), esc(g.get("answerable_from_image"))))
        if g.get("region_prior"):
            rp = g["region_prior"]
            L.append(r"\textbf{Region prior (TRAIN):} %s favors %s \,(%s vs %s).\\" % (
                esc(rp.get("region", "")), esc(g["diagnosis"]),
                esc(rp.get("true")), esc(rp.get("distractor"))))
        L.append(r"\textbf{Decisive cue:} \emph{%s}\\" % esc(decided))
        cf = it["counterfactual"]
        L.append(r"\textbf{Counterfactual (%s):} swap $\rightarrow$ %s. %s\\" % (
            "control" if cf.get("control") else "expect shift",
            esc(cf.get("swap_location_to", "")), esc(cf.get("expected_shift", ""))))
        ev = it["lookalike"].get("evidence") or {}
        clip = ev.get("clip", {})
        L.append(r"\textbf{Two-level evidence:} CLIP organ-matched cross-kNN $=%s$; "
                 r"web: ``\emph{%s}'' \footnotesize\url{%s}" % (
                     esc(clip.get("matched_cross_knn")), esc((ev.get("web_quote") or "")[:160]),
                     ev.get("web_source_url", "")))
    L.append(r"\end{document}")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "geophyto_qa_sample.pdf"))
    args = ap.parse_args()
    tex = build_tex(args.out)
    workdir = os.path.join(ROOT, "figures")
    texpath = os.path.join(workdir, "geophyto_qa_sample.tex")
    open(texpath, "w").write(tex)
    for _ in range(2):
        r = subprocess.run(["pdflatex", "-interaction=nonstopmode", "geophyto_qa_sample.tex"],
                           cwd=workdir, capture_output=True, text=True)
    pdf = os.path.join(workdir, "geophyto_qa_sample.pdf")
    if os.path.exists(pdf):
        os.replace(pdf, args.out)
        print("wrote", args.out)
    else:
        print("PDF FAILED\n", r.stdout[-1500:])


if __name__ == "__main__":
    main()
