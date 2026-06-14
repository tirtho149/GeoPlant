#!/usr/bin/env python3
"""
collect_swarm_reasoning.py — harvest PLANT-ONLY visual reasoning from the
PRESAGE plantswarm and key it by Bugwood image id, for the GeoPhyto-CoT VQA.

The PRESAGE plantswarm (../PRESAGE) is a swarm of ~22 single-feature visual
specialists (leaf / stem / root / reproductive / sign / whole-plant patterns)
that look **only at the photograph** and emit image-grounded observations — by
construction it carries NO background / scene / street-level reasoning, only the
plant portion. That is exactly the visual evidence the geolocation CoT should
PERCEIVE from. This script reads the swarm's trace JSONL and, per image, distils
the deduplicated plant-only observations into a compact record the VQA builder
slots into the CoT's PERCEIVE step.

Input  : PRESAGE phase0r trace JSONL (specialist_outputs[].deltas with
         {field, image_shows, image_quote} + per-specialist reasoning).
Output : swarm_reasoning.jsonl, one line per image:
         {"image_number", "crop", "disease",
          "visual_evidence": [{"organ","field","observation","quote","agent"}],
          "perceive": "<one plant-only sentence joining the salient observations>"}

Usage:
    python scripts/collect_swarm_reasoning.py \
        --trace ../PRESAGE/artifacts/phase0r_traces/phase0r_traces.jsonl \
        --out swarm_reasoning.jsonl
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_TRACE = os.path.join(ROOT, "..", "PRESAGE",
                             "artifacts", "phase0r_traces", "phase0r_traces.jsonl")

# field-prefix -> plant organ family (for grouping / readable PERCEIVE)
ORGAN_OF = {
    "leaf": "leaf", "stem": "stem", "root": "root", "crown": "crown",
    "flower": "flower", "fruit": "fruit", "spor": "signs", "wilt": "whole-plant",
    "defoli": "whole-plant", "spatial": "whole-plant", "concentric": "lesion",
    "color": "lesion", "look": "lesion", "severity": "whole-plant",
}
EMPTY = {"", "(not specified)", "(none)", "none", "n/a", "not specified",
         "no change", "no difference", "(no change)", "same"}


def organ_of(field):
    f = (field or "").lower()
    for pre, organ in ORGAN_OF.items():
        if f.startswith(pre) or pre in f:
            return organ
    return "plant"


def clean(s):
    return re.sub(r"\s+", " ", (s or "").strip())


def harvest(trace_path):
    by_img = collections.OrderedDict()
    n_rec = 0
    with open(trace_path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            n_rec += 1
            raw_id = str(r.get("primary_image_id") or "")
            m = re.search(r"(\d+)", raw_id)
            if not m:
                continue
            img = m.group(1)
            slot = by_img.setdefault(img, {
                "image_number": img, "crop": r.get("crop", ""),
                "disease": r.get("disease", ""), "_seen": set(), "visual_evidence": [],
            })
            for so in r.get("specialist_outputs", []):
                agent = so.get("agent_name", "")
                for d in (so.get("deltas") or []):
                    obs = clean(d.get("image_shows"))
                    if not obs or obs.lower() in EMPTY:
                        continue
                    field = d.get("field", "other")
                    key = (field, obs.lower())
                    if key in slot["_seen"]:
                        continue
                    slot["_seen"].add(key)
                    slot["visual_evidence"].append({
                        "organ": organ_of(field), "field": field,
                        "observation": obs, "quote": clean(d.get("image_quote")),
                        "agent": agent,
                    })
    return by_img, n_rec


def make_perceive(ev):
    """One plant-only sentence joining the salient observations, organ-ordered."""
    order = ["leaf", "lesion", "stem", "signs", "fruit", "flower", "root",
             "crown", "whole-plant", "plant"]
    ev_sorted = sorted(ev, key=lambda e: order.index(e["organ"]) if e["organ"] in order else 99)
    phrases = []
    seen = set()
    for e in ev_sorted[:6]:
        obs = e["observation"].rstrip(".")
        low = obs.lower()
        if low in seen:
            continue
        seen.add(low)
        phrases.append(obs)
    if not phrases:
        return ""
    return ("On the plant itself the swarm observes: " + "; ".join(phrases)
            + ". (No background or scene cues are used.)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", default=DEFAULT_TRACE)
    ap.add_argument("--out", default=os.path.join(ROOT, "swarm_reasoning.jsonl"))
    args = ap.parse_args()

    if not os.path.exists(args.trace):
        sys.exit(f"trace not found: {args.trace}")

    by_img, n_rec = harvest(args.trace)
    n_with_ev = 0
    with open(args.out, "w") as fh:
        for img, slot in by_img.items():
            slot.pop("_seen", None)
            slot["perceive"] = make_perceive(slot["visual_evidence"])
            slot["n_evidence"] = len(slot["visual_evidence"])
            if slot["n_evidence"]:
                n_with_ev += 1
            fh.write(json.dumps(slot) + "\n")

    ev_counts = [s["n_evidence"] for s in by_img.values()]
    organs = collections.Counter(e["organ"] for s in by_img.values()
                                 for e in s["visual_evidence"])
    print(f"[trace] {n_rec} passes -> {len(by_img)} distinct images")
    print(f"[harvest] {n_with_ev} images carry >=1 plant-only observation")
    if ev_counts:
        ev_counts.sort()
        print(f"[evidence] per-image observations: "
              f"min={ev_counts[0]} median={ev_counts[len(ev_counts)//2]} max={ev_counts[-1]}")
    print(f"[organs] {dict(organs.most_common())}")
    print(f"[write] {args.out}")
    # show one
    ex = next((s for s in by_img.values() if s["n_evidence"] >= 3), None)
    if ex:
        print(f"\n--- sample image {ex['image_number']} ({ex['crop']} / {ex['disease']}) ---")
        print("PERCEIVE:", ex["perceive"])


if __name__ == "__main__":
    main()
