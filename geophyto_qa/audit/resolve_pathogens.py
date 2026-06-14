"""
S09 — resolve pathogens & extract Lane-B pair-claims.   [CPU]

Maps every Lane-B (host, disease) to a pathogen binomial using the enriched CSV's
`Scientific Name` column, with a disease-level fallback (covers 107/107 pathogens;
only `watermelon / Unknown Virus` is unresolvable). Emits:
  * pathogen_worklist.json : {binomial: {"appears_as": [...], "items": N}}  (S10 input)
  * pair_claims.json       : every Lane-B (host, true, distractor, region) claim the
                             prior asserts, with the prior's stored weights (S11 input)

Usage:
  python -m geophyto_qa.audit.resolve_pathogens \
      --jsonl geophyto_qa.jsonl --csv BugWood_Diseases_enriched.csv \
      --out-pathogens geophyto_qa/audit/pathogen_worklist.json \
      --out-claims    geophyto_qa/audit/pair_claims.json
"""
import argparse, csv, json, os
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def build_sci_maps(csv_path):
    pair_c, dis_c = defaultdict(Counter), defaultdict(Counter)
    with open(csv_path, newline="") as f:
        for r in csv.DictReader(f):
            crop = (r.get("NormCrop") or "").strip().lower()
            dis = (r.get("NormDisease") or "").strip().lower()
            sci = (r.get("Scientific Name") or "").strip()
            if dis and sci:
                if crop:
                    pair_c[(crop, dis)][sci] += 1
                dis_c[dis][sci] += 1
    pair_map = {k: v.most_common(1)[0][0] for k, v in pair_c.items()}
    dis_map = {k: v.most_common(1)[0][0] for k, v in dis_c.items()}
    return pair_map, dis_map


def resolver(pair_map, dis_map):
    def resolve(host, dis):
        h, d = (host or "").lower(), (dis or "").lower()
        if (h, d) in pair_map:
            return pair_map[(h, d)]
        return dis_map.get(d)
    return resolve


def lane(rec):
    return (rec.get("lookalike", {}) or {}).get("clip_lane_hint") or rec.get("lane")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", default=os.path.join(ROOT, "geophyto_qa.jsonl"))
    ap.add_argument("--csv", default=os.path.join(ROOT, "BugWood_Diseases_enriched.csv"))
    ap.add_argument("--out-pathogens", default=os.path.join(ROOT, "geophyto_qa", "audit", "pathogen_worklist.json"))
    ap.add_argument("--out-claims", default=os.path.join(ROOT, "geophyto_qa", "audit", "pair_claims.json"))
    a = ap.parse_args()

    pair_map, dis_map = build_sci_maps(a.csv)
    resolve = resolver(pair_map, dis_map)

    ctx = defaultdict(Counter)          # binomial -> host/disease appearances
    claims = {}                          # (host,true,dist,region) -> claim dict
    unresolved = Counter()
    with open(a.jsonl) as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            if lane(r) != "image_ambiguous":
                continue
            g = r.get("gold", {}) or {}
            gr = r.get("grounding", {}) or {}
            host, region = gr.get("host"), gr.get("region")
            true, dist = g.get("diagnosis"), g.get("ruled_out")
            if not (host and region and true and dist):
                continue
            bt, bd = resolve(host, true), resolve(host, dist)
            for d, b in ((true, bt), (dist, bd)):
                if b:
                    ctx[b][f"{host}/{d}"] += 1
                else:
                    unresolved[f"{host}/{d}"] += 1
            key = (host, true, dist, region)
            if key not in claims:
                rp = g.get("region_prior", {}) or {}
                claims[key] = {
                    "host": host, "true": true, "distractor": dist, "region": region,
                    "sci_true": bt, "sci_dist": bd,
                    "prior_true": rp.get("true"), "prior_dist": rp.get("distractor"),
                    "items": 0,
                }
            claims[key]["items"] += 1

    worklist = {b: {"appears_as": [k for k, _ in c.most_common(3)],
                    "items": sum(c.values())}
                for b, c in sorted(ctx.items(), key=lambda x: -sum(x[1].values()))}

    os.makedirs(os.path.dirname(a.out_pathogens), exist_ok=True)
    json.dump(worklist, open(a.out_pathogens, "w"), indent=1)
    json.dump(list(claims.values()), open(a.out_claims, "w"), indent=1)

    print(f"pathogens to research : {len(worklist)}  -> {a.out_pathogens}")
    print(f"Lane-B pair-claims    : {len(claims)} (items {sum(c['items'] for c in claims.values())})"
          f"  -> {a.out_claims}")
    if unresolved:
        print(f"UNRESOLVED (no binomial): {len(unresolved)} -> {dict(unresolved)}")


if __name__ == "__main__":
    main()
