"""
Merge the lay-augmentation Workflow output (graph.lay layer) back into the
generated graph records. Idempotent.

  python -m geophyto_qa.persist_lay --workflow-dir <wf transcript dir>
"""
from __future__ import annotations
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from geophyto_qa.graphgen import GEN_DIR   # noqa: E402

LAY_KEYS = ("farmer_lay_report", "decisive_lay_a", "decisive_lay_b",
            "decisive_micro_a", "decisive_micro_b")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workflow-dir", required=True)
    args = ap.parse_args()
    merged = missing = 0
    for line in open(os.path.join(args.workflow_dir, "journal.jsonl")):
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get("type") != "result" or not isinstance(rec.get("result"), dict):
            continue
        r = rec["result"]
        pid = r.get("pair_id")
        if not pid or "farmer_lay_report" not in r:
            continue
        path = os.path.join(GEN_DIR, pid + ".json")
        if not os.path.exists(path):
            missing += 1
            continue
        g = json.load(open(path))
        g["graph"]["lay"] = {k: r.get(k) for k in LAY_KEYS}
        json.dump(g, open(path, "w"), indent=2)
        merged += 1
    print(f"merged lay layer into {merged} graphs (missing graph file: {missing})")


if __name__ == "__main__":
    main()
