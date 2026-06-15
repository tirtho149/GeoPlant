"""
geophyto_qa.quality.disease_label_judge  —  STEP 0: dataset label quality check
===============================================================================
Two-layer LLM-as-judge over the dataset's crop/disease LABELS, ported from
tirtho149/SAGE (SageQualityChecker/disease_label_judge.py) and adapted to read
the crop/disease registry straight from the active ImageFolder dataset
(geophyto_qa.data_source) instead of a hardcoded CSV.

  Layer 1 — crop validation  : VALID | INVALID | NON_CROP | MISSPELLED_OR_UNSTANDARDISED
  Layer 2 — disease labels    : CORRECT | INCORRECT | QUESTIONABLE  (+ similar/duplicate groups)

Only labels that could actually become items are judged: a (crop, disease) is
included when it has >= --min-imgs images (use --all to judge everything).

Outputs (under geophyto_qa/quality/):
  crop_disease_registry.csv        the exact crop/disease list judged (provenance)
  disease_label_full_report.json   per-crop verdicts (consumed by quality.label_gate)
  disease_label_full_progress.txt  running log

Judge = the `claude` CLI (no API key). Resumable: completed crops are skipped.

Run:  sbatch geophyto_qa/slurm/step00_label_judge.slurm
Smoke: python -m geophyto_qa.quality.disease_label_judge --limit 3
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))
from geophyto_qa.data_source import load_rows, DEFAULT_SOURCE   # noqa: E402

REGISTRY_PATH = HERE / "crop_disease_registry.csv"
OUTPUT_PATH = HERE / "disease_label_full_report.json"
PROGRESS_PATH = HERE / "disease_label_full_progress.txt"
JUDGE_MODEL = os.environ.get("GPQA_JUDGE_MODEL", "claude-opus-4-8")

# ── prompts (verbatim from SAGE) ───────────────────────────────────────────── #
CROP_VALIDATION_PROMPT = """\
You are an expert agronomist. Apply the decision tree below to the crop name given.

DECISION TREE:
  Node A: Is this entry a real plant or plant-based crop (not a spreadsheet label, number, or non-plant)?
    → NO  → verdict: INVALID   (e.g. "TOTAL", "N/A", a row header)
    → YES → Node B
  Node B: Is it grown as an agricultural or horticultural crop (food, fibre, spice, timber, ornamental)?
    → NO  → verdict: NON_CROP  (purely wild plant, a pathogen name, not cultivated)
    → YES → Node C
  Node C: Is the common crop name spelled correctly and reasonably standardised?
    → NO  → verdict: MISSPELLED_OR_UNSTANDARDISED
    → YES → verdict: VALID

Return ONLY valid JSON (no markdown, no fences):
{
  "crop": "<exact input name>",
  "node_a": "YES" | "NO",
  "node_b": "YES" | "NO" | "N/A",
  "node_c": "YES" | "NO" | "N/A",
  "verdict": "VALID" | "INVALID" | "NON_CROP" | "MISSPELLED_OR_UNSTANDARDISED",
  "canonical_name": "<corrected / standard name, or same if VALID>",
  "category": "<one of: cereal, legume, fruit, vegetable, root_tuber, tree_crop, fiber_crop, oilseed, herb_spice, ornamental, beverage_crop, nut_crop, forage, other>",
  "notes": "<one sentence — only if something is unusual or needs clarification, else empty string>"
}

Crop to evaluate:
"""

DISEASE_JUDGE_PROMPT = """\
You are an expert plant pathologist. Quality-check disease labels for the crop below.

Return ONLY valid JSON (no markdown, no fences):
{
  "crop": "<crop name>",
  "disease_verdicts": [
    {
      "disease": "<label>",
      "verdict": "CORRECT" | "INCORRECT" | "QUESTIONABLE",
      "reason": "<one sentence>"
    }
  ],
  "similar_groups": [
    {
      "diseases": ["<label A>", "<label B>"],
      "reason": "<why these overlap or duplicate>"
    }
  ],
  "summary": "<2-3 sentence quality assessment>"
}

Verdict rules:
  CORRECT      — well-documented disease known to affect this crop.
  INCORRECT    — wrong crop; disease of a completely different plant; or entry is not a disease at all.
  QUESTIONABLE — real disease but label is vague, misspelled, names a pathogen genus instead of a
                 disease, refers to an insect pest or beneficial organism, or is an unusual
                 / unverified association with this crop.

"""


# ── registry from the active dataset ───────────────────────────────────────── #
def build_registry(source=None, min_imgs=12, judge_all=False):
    """{crop: [disease, ...]} for (crop, disease) with >= min_imgs images
    (or every label when judge_all). Also writes crop_disease_registry.csv."""
    counts = collections.Counter()
    for r in load_rows(source):
        counts[(r["crop"], r["disease"])] += 1
    crop_disease = collections.defaultdict(list)
    for (crop, disease), n in counts.items():
        if judge_all or n >= min_imgs:
            crop_disease[crop].append(disease)
    crop_disease = {c: sorted(set(ds)) for c, ds in crop_disease.items()}
    with open(REGISTRY_PATH, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Crop", "Disease", "n_images"])
        for crop in sorted(crop_disease):
            for dis in crop_disease[crop]:
                w.writerow([crop, dis, counts[(crop, dis)]])
    return crop_disease


# ── claude CLI judge ───────────────────────────────────────────────────────── #
def call_claude(prompt: str, model: str, retries: int = 3) -> str:
    for attempt in range(1, retries + 1):
        result = subprocess.run(
            ["claude", "--model", model, "-p", prompt],
            capture_output=True, text=True, timeout=180,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        if attempt < retries:
            time.sleep(4 * attempt)
    raise RuntimeError(f"claude CLI failed after {retries} retries. "
                       f"stderr: {result.stderr.strip()[:200]}")


def parse_json_from_text(text: str) -> dict:
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group())
        raise


def log(text: str) -> None:
    print(text, flush=True)
    with open(PROGRESS_PATH, "a", encoding="utf-8") as f:
        f.write(text + "\n")


def validate_crop(crop: str, model: str) -> dict:
    try:
        result = parse_json_from_text(call_claude(CROP_VALIDATION_PROMPT + crop, model))
        result.setdefault("crop", crop)
        return result
    except Exception as e:
        return {"crop": crop, "verdict": "ERROR", "error": str(e), "parse_error": True}


def judge_diseases(crop: str, diseases: list, model: str) -> dict:
    disease_list = "\n".join(f"- {d}" for d in diseases)
    prompt = DISEASE_JUDGE_PROMPT + f"Crop: {crop}\n\nDiseases:\n{disease_list}"
    try:
        result = parse_json_from_text(call_claude(prompt, model))
        result.setdefault("crop", crop)
        return result
    except Exception as e:
        return {"crop": crop, "error": str(e), "parse_error": True}


# ── main ───────────────────────────────────────────────────────────────────── #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=DEFAULT_SOURCE,
                    help="ImageFolder dataset dir (default: GPQA_SOURCE / CyAg)")
    ap.add_argument("--min-imgs", type=int, default=12,
                    help="only judge (crop,disease) with >= this many images")
    ap.add_argument("--all", action="store_true", help="judge every label regardless of count")
    ap.add_argument("--model", default=JUDGE_MODEL)
    ap.add_argument("--limit", type=int, default=None, help="smoke: cap number of crops")
    args = ap.parse_args()

    PROGRESS_PATH.write_text("", encoding="utf-8")
    log("TWO-LAYER CROP DISEASE LABEL QUALITY REPORT (step 0)\n" + "=" * 70)
    log(f"source={args.source}  model={args.model}  min_imgs={args.min_imgs}  all={args.all}")

    crop_disease_map = build_registry(args.source, args.min_imgs, args.all)
    crops = sorted(crop_disease_map)
    if args.limit:
        crops = crops[:args.limit]
    log(f"judging {len(crops)} crops / "
        f"{sum(len(crop_disease_map[c]) for c in crops)} disease labels "
        f"-> {OUTPUT_PATH}\n")

    saved = {}
    if OUTPUT_PATH.exists():
        try:
            for r in json.load(open(OUTPUT_PATH, encoding="utf-8")):
                if r.get("crop") and not r.get("parse_error"):
                    saved[r["crop"]] = r
            if saved:
                log(f"Resuming: {len(saved)} crops already done — skipping.\n")
        except Exception:
            pass

    all_results = []
    total = len(crops)
    for idx, crop in enumerate(crops, start=1):
        if crop in saved:
            all_results.append(saved[crop])
            print(f"[{idx}/{total}] {crop} — skipped (saved)", flush=True)
            continue

        log(f"\n{'#'*70}\n# [{idx}/{total}]  {crop}  — LAYER 1 crop validation\n{'#'*70}")
        cv = validate_crop(crop, args.model)
        record = {"crop": crop, "crop_validation": cv}
        log(f"  verdict={cv.get('verdict')}  canonical={cv.get('canonical_name', '')}  "
            f"category={cv.get('category', '')}")

        if cv.get("verdict") in ("INVALID", "NON_CROP", "ERROR"):
            record["disease_check"] = {"skipped": True, "reason": f"crop {cv.get('verdict')}"}
            log(f"  -> skipping disease check ({cv.get('verdict')})")
        else:
            diseases = crop_disease_map[crop]
            log(f"  LAYER 2 — judging {len(diseases)} diseases ...")
            dc = judge_diseases(crop, diseases, args.model)
            record["disease_check"] = dc
            vs = dc.get("disease_verdicts", [])
            inc = sum(1 for v in vs if v.get("verdict") == "INCORRECT")
            q = sum(1 for v in vs if v.get("verdict") == "QUESTIONABLE")
            log(f"    {len(vs)} verdicts: INCORRECT={inc} QUESTIONABLE={q} "
                f"similar_groups={len(dc.get('similar_groups', []))}")

        all_results.append(record)
        json.dump(all_results, open(OUTPUT_PATH, "w", encoding="utf-8"), indent=2)
        time.sleep(1)

    # aggregate
    bad = sum(1 for r in all_results
              if r.get("crop_validation", {}).get("verdict") in ("INVALID", "NON_CROP", "ERROR"))
    mis = sum(1 for r in all_results
              if r.get("crop_validation", {}).get("verdict") == "MISSPELLED_OR_UNSTANDARDISED")
    td = ti = tq = 0
    for r in all_results:
        dc = r.get("disease_check", {})
        if dc.get("skipped"):
            continue
        vs = dc.get("disease_verdicts", [])
        td += len(vs)
        ti += sum(1 for v in vs if v.get("verdict") == "INCORRECT")
        tq += sum(1 for v in vs if v.get("verdict") == "QUESTIONABLE")
    log("\n" + "=" * 70 + "\nOVERALL LABEL QUALITY\n" + "=" * 70)
    log(f"  crops: {len(all_results)}  invalid/non-crop: {bad}  misspelled: {mis}  "
        f"valid: {len(all_results) - bad - mis}")
    log(f"  diseases: {td}  incorrect: {ti}  questionable: {tq}")
    log(f"\nreport -> {OUTPUT_PATH}\nNext: quality.label_gate uses this to drop bad labels before step 1.")


if __name__ == "__main__":
    main()
