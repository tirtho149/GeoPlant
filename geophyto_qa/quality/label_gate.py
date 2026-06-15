"""
geophyto_qa.quality.label_gate
==============================
Apply the step-0 label-quality report (disease_label_judge) to the dataset rows
BEFORE mining. If the report is absent it is a no-op, so the pipeline still runs
without step 0.

Rules:
  * crop verdict INVALID / NON_CROP / ERROR        -> drop all rows of that crop
  * disease verdict INCORRECT                       -> drop those (crop, disease) rows
  * crop verdict MISSPELLED_OR_UNSTANDARDISED       -> rename crop to canonical_name
  (QUESTIONABLE is kept — flagged, not removed.)
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REPORT = os.path.join(HERE, "disease_label_full_report.json")


def load_gate(report_path: str = DEFAULT_REPORT):
    """Return (bad_crops, incorrect_pairs, canonical) from the report, or empty
    sets/maps if there is no report yet."""
    bad_crops, incorrect_pairs, canonical = set(), set(), {}
    if not os.path.exists(report_path):
        return bad_crops, incorrect_pairs, canonical
    for r in json.load(open(report_path, encoding="utf-8")):
        crop = r.get("crop")
        cv = r.get("crop_validation", {}) or {}
        v = cv.get("verdict")
        if v in ("INVALID", "NON_CROP", "ERROR"):
            bad_crops.add(crop)
            continue
        if v == "MISSPELLED_OR_UNSTANDARDISED" and cv.get("canonical_name"):
            canonical[crop] = cv["canonical_name"].strip()
        for dv in (r.get("disease_check", {}) or {}).get("disease_verdicts", []):
            if dv.get("verdict") == "INCORRECT":
                incorrect_pairs.add((crop, dv.get("disease")))
    return bad_crops, incorrect_pairs, canonical


def filter_rows(rows, report_path: str = DEFAULT_REPORT):
    """Drop rows failing the label gate; remap misspelled crop names. No-op if
    no report exists. Returns (filtered_rows, stats)."""
    bad_crops, incorrect_pairs, canonical = load_gate(report_path)
    if not (bad_crops or incorrect_pairs or canonical):
        return rows, {"applied": False}
    out, dropped_crop, dropped_disease, renamed = [], 0, 0, 0
    for row in rows:
        c = row["crop"]
        if c in bad_crops:
            dropped_crop += 1
            continue
        if (c, row["disease"]) in incorrect_pairs:
            dropped_disease += 1
            continue
        if c in canonical:
            row = dict(row)
            row["crop"] = canonical[c]
            row["host_common"] = canonical[c]
            renamed += 1
        out.append(row)
    return out, {"applied": True, "kept": len(out), "dropped_bad_crop": dropped_crop,
                 "dropped_incorrect_disease": dropped_disease, "renamed_misspelled": renamed,
                 "n_bad_crops": len(bad_crops), "n_incorrect_pairs": len(incorrect_pairs)}
