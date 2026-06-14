"""
S11 — score the contributor-count prior against the external range evidence.   [CPU]

For each Lane-B pair-claim ("in region R the prior favors TRUE over DISTRACTOR"),
look up both members' cited US range (web_range_evidence.json) and decide:

  agree              TRUE present in R, DISTRACTOR absent in R          -> prior justified
  flip               DISTRACTOR present in R, TRUE absent in R          -> MISLABELED gold
  non_discriminative both present in R (co-occur)                       -> Lane-B premise fails
                     (geography cannot break the tie for this pair)
  undetermined       either member has no credible range info / no R    -> reported, never dropped

Region membership uses regions_present; regions_core (severe/endemic) breaks a
"both present" tie when exactly one member is core in R (-> agree/flip), else
non_discriminative. GBIF is NOT used (collection bias); evidence is citation-based.

Usage:
  python -m geophyto_qa.audit.score_prior \
      --claims geophyto_qa/audit/pair_claims.json \
      --ranges geophyto_qa/lookalike/web_range_evidence.json \
      --out    geophyto_qa/audit/prior_audit.json
"""
import argparse, json, os
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def present(rng, region):
    if not rng:
        return None                      # unknown
    if rng.get("cosmopolitan"):
        return True
    return region in (rng.get("regions_present") or [])


def core(rng, region):
    return bool(rng) and region in (rng.get("regions_core") or [])


def verdict_for(claim, ranges):
    rt = ranges.get(claim.get("sci_true") or "")
    rd = ranges.get(claim.get("sci_dist") or "")
    if not rt or not rd:
        return "undetermined", "missing range evidence for a member"
    region = claim["region"]
    pt, pd = present(rt, region), present(rd, region)
    if pt is None or pd is None:
        return "undetermined", "region not assessable"
    if pt and not pd:
        return "agree", "true present, distractor absent in region"
    if pd and not pt:
        return "flip", "distractor present, true absent in region"
    if pt and pd:
        ct, cd = core(rt, region), core(rd, region)
        if ct and not cd:
            return "agree", "both present; true is core in region"
        if cd and not ct:
            return "flip", "both present; distractor is core in region"
        return "non_discriminative", "both members occur in region"
    return "undetermined", "neither member present in region"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--claims", default=os.path.join(ROOT, "geophyto_qa", "audit", "pair_claims.json"))
    ap.add_argument("--ranges", default=os.path.join(ROOT, "geophyto_qa", "lookalike", "web_range_evidence.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "geophyto_qa", "audit", "prior_audit.json"))
    a = ap.parse_args()

    claims = json.load(open(a.claims))
    ranges = json.load(open(a.ranges)) if os.path.exists(a.ranges) else {}

    results, by_combo, by_item = [], Counter(), Counter()
    for c in claims:
        v, why = verdict_for(c, ranges)
        rec = dict(c); rec["verdict"] = v; rec["why"] = why
        results.append(rec)
        by_combo[v] += 1
        by_item[v] += c.get("items", 0)

    adjudicable = by_combo["agree"] + by_combo["flip"] + by_combo["non_discriminative"]
    summary = {
        "n_pathogens_with_ranges": len(ranges),
        "lane_b_combos": len(claims),
        "by_combo": dict(by_combo),
        "by_item": dict(by_item),
        "adjudicable_combos": adjudicable,
        "results": sorted(results, key=lambda r: -r.get("items", 0)),
    }
    json.dump(summary, open(a.out, "w"), indent=2)

    n = len(claims) or 1
    print("=" * 60)
    print("PRIOR AUDIT  (contributor prior vs cited external range)")
    print("=" * 60)
    print(f"pathogens with range evidence: {len(ranges)}")
    print(f"Lane-B pair-combos: {len(claims)}  items: {sum(by_item.values())}")
    for v in ("agree", "flip", "non_discriminative", "undetermined"):
        print(f"  {v:18s}: {by_combo[v]:4d} combos ({100*by_combo[v]/n:5.1f}%) | {by_item[v]} items")
    if adjudicable:
        bad = by_combo["flip"] + by_combo["non_discriminative"]
        print(f"\nprior FAILS (flip+non_discriminative): {bad}/{adjudicable} adjudicable "
              f"= {100*bad/adjudicable:.0f}%")
    print(f"\n-> {a.out}")


if __name__ == "__main__":
    main()
