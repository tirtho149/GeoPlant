"""
Reassemble the disease-label-judge Workflow output into the original
SAGE `disease_label_full_report.json` shape, and apply its verdicts as the
INITIAL quality gate on the look-alike confirmed set:

  * crop verdict INVALID / NON_CROP  -> drop all that crop's pairs
  * disease verdict INCORRECT        -> drop pairs containing that disease
  * malformed label ("Genus X")      -> drop (names a genus, not a disease)
  * disease verdict QUESTIONABLE     -> flag (kept, recorded)
  * similar_groups                   -> drop a pair ONLY when the group's reason
                                        signals a TRUE synonym/duplicate
                                        (anamorph/teleomorph/same fungus/...).
                                        Genuine look-alikes ("confused, distinct
                                        fungi") are the TARGET and are kept.

Usage:
  python quality/apply_judge.py --workflow-dir <wf transcript dir>
"""
from __future__ import annotations
import argparse, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REPORT = os.path.join(HERE, "disease_label_full_report.json")
CONF = os.path.join(ROOT, "geophyto_qa", "lookalike", "confirmed_lookalikes.json")


def results_from_journal(wf_dir):
    out = {}
    for line in open(os.path.join(wf_dir, "journal.jsonl")):
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get("type") == "result" and isinstance(rec.get("result"), dict):
            r = rec["result"]
            if "crop_validation" in r and r.get("crop"):
                out[r["crop"]] = r
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workflow-dir", required=True)
    args = ap.parse_args()

    res = results_from_journal(args.workflow_dir)
    # write report in the original list-of-records shape
    report = [{"crop": c, "crop_validation": r["crop_validation"],
               "disease_check": r["disease_check"]} for c, r in sorted(res.items())]
    json.dump(report, open(REPORT, "w"), indent=2)

    # NOTE: similar_groups is NOT a drop signal — it flags BOTH true synonyms and
    # genuine look-alikes (our target). True synonyms are removed upstream by the
    # genus/anamorph-alias check in verify_pairs; here we only act on hard
    # label-quality verdicts. We still record similar_groups as corroboration.
    bad_crops, bad_dis, questionable, sim_corroborate = set(), set(), set(), {}
    for c, r in res.items():
        if r["crop_validation"]["verdict"] in ("INVALID", "NON_CROP"):
            bad_crops.add(c)
        for v in r["disease_check"].get("disease_verdicts", []):
            if v["verdict"] == "INCORRECT":
                bad_dis.add((c, v["disease"]))
            elif v["verdict"] == "QUESTIONABLE":
                questionable.add((c, v["disease"]))
        for g in r["disease_check"].get("similar_groups", []):
            sim_corroborate[(c, frozenset(g["diseases"]))] = g.get("reason", "")

    # apply to confirmed set
    conf = json.load(open(CONF))
    dropped = []
    for pid, d in conf.items():
        if not d.get("confirmed"):
            continue
        crop, a, b = d["crop"], d["member_a"], d["member_b"]
        reason = None
        if crop in bad_crops:
            reason = "crop INVALID/NON_CROP"
        elif (crop, a) in bad_dis or (crop, b) in bad_dis:
            reason = "member label INCORRECT"
        elif a.startswith("Genus ") or b.startswith("Genus "):
            reason = "malformed label (names a genus, not a disease)"
        if reason:
            d["confirmed"] = False
            d["dropped_reason"] = "judge: " + reason
            dropped.append((pid, reason))
            continue
        if (crop, a) in questionable or (crop, b) in questionable:
            d["judge_questionable"] = True
        # record judge corroboration of the look-alike (a similar_group naming both)
        for (gc, members), why in sim_corroborate.items():
            if gc == crop and a in members and b in members:
                d["judge_similar_group"] = why
                break
    json.dump(conf, open(CONF, "w"), indent=2)

    n_conf = sum(1 for d in conf.values() if d.get("confirmed"))
    print(f"report -> {REPORT}  ({len(report)} crops)")
    print(f"judge gate: bad_crops={len(bad_crops)} incorrect_labels={len(bad_dis)} "
          f"questionable={len(questionable)} similar_groups={len(sim_corroborate)}")
    print(f"dropped {len(dropped)} confirmed pairs -> {n_conf} remain")
    for pid, why in dropped:
        print("  DROP", pid, "::", why)
    if bad_dis:
        print("INCORRECT labels:", sorted(bad_dis)[:20])


if __name__ == "__main__":
    main()
