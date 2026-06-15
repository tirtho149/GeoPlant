"""
geophyto_qa.lookalike.web_confirm_cli  —  STEP 3 (batch / claude CLI variant)
============================================================================
Web-confirm look-alike pairs via the `claude` CLI instead of the Claude Code
Workflow engine, so the GATE can run inside a plain SLURM job (used by the
per-crop full sweep, e.g. soybean — small pair counts).

For each candidate pair it asks Claude whether the two diseases of that crop are
documented look-alikes (using web search if available, else the most authoritative
extension/university/gov source it knows), and stores the evidence via
geophyto_qa.lookalike.web_verify.record (same store + credibility gate as the
Workflow path → lookalike/web_evidence.json). Resumable: already-recorded pairs
are skipped.

Run:  python -m geophyto_qa.lookalike.web_confirm_cli --pairs geophyto_qa/pairs/candidates.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
ROOT = os.path.dirname(PKG)
sys.path.insert(0, ROOT)
from geophyto_qa.quality.disease_label_judge import call_claude, parse_json_from_text  # noqa: E402
from geophyto_qa.lookalike.web_verify import record, load_evidence                     # noqa: E402

MODEL = os.environ.get("GPQA_WEB_MODEL", "claude-opus-4-8")

PROMPT = """\
You are an expert plant pathologist with web access. Decide whether the two
diseases below, on the SAME crop, are genuinely confused / look-alikes — i.e. a
credible source documents that growers or diagnosticians mistake one for the other
(similar visible symptoms). Search the web; prefer extension service, university,
government, or peer-reviewed sources.

Return ONLY valid JSON (no markdown, no fences):
{
  "verified": true | false,
  "claim": "<one sentence: why they are confused, or why not>",
  "quote": "<short verbatim snippet from the source supporting confusion; empty if not verified>",
  "source_url": "<the most authoritative URL; empty if none>",
  "source_title": "<page/source title>",
  "source_type": "extension" | "university" | "peer_reviewed" | "gov" | "other",
  "query": "<the search query you used>"
}

Set verified=true ONLY if a credible source actually states the two are confused /
look similar. CROP: {crop}
DISEASE A: {a}
DISEASE B: {b}
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default=os.path.join(PKG, "pairs", "candidates.json"))
    ap.add_argument("--top", type=int, default=None, help="only the top-N ranked pairs")
    ap.add_argument("--model", default=MODEL)
    args = ap.parse_args()

    pairs = json.load(open(args.pairs))["pairs"]
    if args.top:
        pairs = pairs[:args.top]
    done = set(load_evidence())
    print(f"[web_confirm_cli] {len(pairs)} pairs | model={args.model} | "
          f"{len(done)} already recorded", flush=True)

    n_ok = 0
    for i, p in enumerate(pairs, 1):
        pid = p["pair_id"]
        if pid in done:
            continue
        a, b = p["member_a"]["disease"], p["member_b"]["disease"]
        prompt = PROMPT.format(crop=p["crop"], a=a, b=b)
        try:
            r = parse_json_from_text(call_claude(prompt, args.model))
        except Exception as e:
            print(f"  [{i}/{len(pairs)}] {pid} ERROR: {e}", flush=True)
            continue
        rec = record(pid, p["crop"], a, b,
                     quote=r.get("quote", ""), source_url=r.get("source_url", ""),
                     source_title=r.get("source_title", ""), claim=r.get("claim", ""),
                     source_type=r.get("source_type", ""), query=r.get("query", ""),
                     verified=bool(r.get("verified")))
        n_ok += rec["verified"]
        print(f"  [{i}/{len(pairs)}] {pid}: verified={rec['verified']} "
              f"({rec['source_type']}) {p['crop']}: {a} vs {b}", flush=True)

    print(f"[web_confirm_cli] verified {n_ok} pairs -> {os.path.join(HERE, 'web_evidence.json')}")


if __name__ == "__main__":
    main()
