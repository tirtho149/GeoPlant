"""
Persist the results of the full-sweep Workflow (web-verify + graph-gen) from its
on-disk journal into the stores the build reads:
  * web evidence  -> geophyto_qa/lookalike/web_evidence.json
  * decision graphs -> geophyto_qa/graphs/generated/*.json

Workflow agents echo `pair_id`, so each journal `result` is self-identifying:
web results carry `confusable_documented`; graph results carry `forks`.

Usage:
  python -m geophyto_qa.lookalike.persist_sweep --workflow-dir <wf transcript dir>
"""
from __future__ import annotations
import argparse, glob, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
ROOT = os.path.dirname(PKG)
sys.path.insert(0, ROOT)
from geophyto_qa.schema import validate_graph                 # noqa: E402
from geophyto_qa.graphgen import save_generated               # noqa: E402
from geophyto_qa.lookalike.web_verify import record, CREDIBLE_TYPES  # noqa: E402

CAND = os.path.join(PKG, "pairs", "candidates.json")


def _disease(m):
    # candidates.json may store member as a dict ({"disease": ...}) or a slim string
    return m["disease"] if isinstance(m, dict) else m


def load_pair_meta():
    out = {}
    for p in json.load(open(CAND))["pairs"]:
        out[p["pair_id"]] = (p["crop"], _disease(p["member_a"]), _disease(p["member_b"]))
    return out


def iter_results(wf_dir):
    for line in open(os.path.join(wf_dir, "journal.jsonl")):
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get("type") == "result" and isinstance(rec.get("result"), dict):
            yield rec["result"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workflow-dir", required=True)
    args = ap.parse_args()
    meta = load_pair_meta()

    n_web = n_web_ok = n_graph = n_graph_bad = 0
    seen_web, seen_graph = set(), set()
    for res in iter_results(args.workflow_dir):
        pid = res.get("pair_id")
        if not pid or pid not in meta:
            continue
        crop, a, b = meta[pid]
        if "confusable_documented" in res and pid not in seen_web:        # web result
            seen_web.add(pid)
            n_web += 1
            stype = res.get("source_type", "other")
            verified = bool(res.get("confusable_documented") and res.get("quote")
                            and stype in CREDIBLE_TYPES)
            record(pid, crop, a, b, quote=res.get("quote", ""),
                   source_url=res.get("source_url", ""), source_title=res.get("source_title", ""),
                   claim="", source_type=stype, verified=verified)
            n_web_ok += int(verified)
        elif "forks" in res and pid not in seen_graph:                   # graph result
            seen_graph.add(pid)
            g = {k: v for k, v in res.items() if k != "pair_id"}
            errs = validate_graph(g)
            if errs or not g.get("confusable"):
                n_graph_bad += 1
                continue
            save_generated(pid, "disease", crop, a, b, g, source="llm-generated (workflow sweep)")
            n_graph += 1

    print(f"web evidence: {n_web} pairs ({n_web_ok} verified)")
    print(f"graphs saved: {n_graph}  (rejected/invalid: {n_graph_bad})")


if __name__ == "__main__":
    main()
