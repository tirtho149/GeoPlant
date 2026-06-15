"""
geophyto_qa.graph_gen_cli  —  STEP 6 (batch / claude CLI variant)
================================================================
Author one discriminator decision graph per web-confirmed pair via the `claude`
CLI instead of the Claude Code Workflow engine, so graph generation can run inside
a plain SLURM job (used by the per-crop full sweep).

Reuses geophyto_qa.graphgen.build_prompt (few-shot exemplars + schema), validates
with schema.validate_graph, and writes to graphs/generated/ via save_generated.
Only pairs that are web-verified (lookalike/web_evidence.json) get a graph, mirroring
the Workflow path. Resumable: pairs that already have a graph file are skipped.

Run:  python -m geophyto_qa.graph_gen_cli --pairs geophyto_qa/pairs/candidates.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from geophyto_qa.graphgen import build_prompt, save_generated, GEN_DIR     # noqa: E402
from geophyto_qa.schema import validate_graph                              # noqa: E402
from geophyto_qa.lookalike.web_verify import load_evidence                 # noqa: E402
from geophyto_qa.quality.disease_label_judge import call_claude, parse_json_from_text  # noqa: E402

MODEL = os.environ.get("GPQA_GRAPH_MODEL", "claude-opus-4-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default=os.path.join(HERE, "pairs", "candidates.json"))
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--all", action="store_true",
                    help="generate for every candidate pair, not just web-verified ones")
    args = ap.parse_args()

    pairs = {p["pair_id"]: p for p in json.load(open(args.pairs))["pairs"]}
    if args.all:
        target = list(pairs)
    else:
        target = [pid for pid, r in load_evidence().items() if r.get("verified") and pid in pairs]
    print(f"[graph_gen_cli] {len(target)} target pairs | model={args.model}", flush=True)

    made = skipped = failed = 0
    for i, pid in enumerate(sorted(target), 1):
        if os.path.exists(os.path.join(GEN_DIR, pid + ".json")):
            skipped += 1
            continue
        p = pairs[pid]
        try:
            graph = parse_json_from_text(call_claude(build_prompt(p), args.model))
        except Exception as e:
            print(f"  [{i}/{len(target)}] {pid} CLAUDE/PARSE ERROR: {e}", flush=True)
            failed += 1
            continue
        errs = validate_graph(graph)
        if errs:
            print(f"  [{i}/{len(target)}] {pid} INVALID GRAPH: {errs[:3]}", flush=True)
            failed += 1
            continue
        save_generated(pid, "disease", p["crop"],
                       p["member_a"]["disease"], p["member_b"]["disease"], graph)
        made += 1
        print(f"  [{i}/{len(target)}] {pid} OK -> graphs/generated/{pid}.json", flush=True)

    print(f"[graph_gen_cli] made {made} | skipped {skipped} (exist) | failed {failed}")


if __name__ == "__main__":
    main()
