#!/usr/bin/env python3
"""
gbif_range.py — geo-informativeness filter over external (GBIF) true-range data
===============================================================================

Turns the raw `gbif_ranges.json` (per-pathogen occurrence facets, fetched by
scripts/fetch_gbif_ranges.py) into a per-pathogen *restriction class* that gates
whether an image of that disease can honestly be localized.

This is the step that would have caught the bread-mold sample before it became an
item: corpus concentration can't tell "truly localized" from "narrowly sampled",
so the decision is made against GBIF's independent global occurrences instead.

Restriction classes
--------------------
  localized     few countries / 1-2 continents, enough records to trust  -> localizable
  regional      intermediate spread                                       -> localizable @ coarse tier
  cosmopolitan  many countries / >=4 continents, or a named generalist    -> INDETERMINATE
  data_poor     too few GBIF records, or no/higher-rank backbone match    -> INDETERMINATE
                (honest: a narrow footprint here may be sampling bias, not range)

Concentration-aware: a pathogen recorded once each in 80 countries is not
"present in 80 ranges". `eff_countries` counts only countries holding a
meaningful share (>= MIN_SHARE of records AND >= MIN_CTRY_RECORDS), trimming the
single-record noise tail that inflates raw country counts.
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DEFAULT_RANGES = os.path.join(ROOT, "gbif_ranges.json")

# --- thresholds (transparent; printed in the build report so they can be tuned) -
MIN_RECORDS = 30          # below this, GBIF range is too sparse to trust -> data_poor
MIN_CTRY_RECORDS = 3      # a country needs >= this many records to "count"
MIN_SHARE = 0.01          # ...and >= this share of the species' total records
LOCALIZED_MAX_CTRY = 6    # eff_countries <= this (and <=2 continents) -> localized
LOCALIZED_MAX_CONT = 2
COSMO_MIN_CTRY = 25       # eff_countries >= this, OR continents >= 4 -> cosmopolitan
COSMO_MIN_CONT = 4

# Named ubiquitous storage / postharvest / soilborne generalists. Genus-level
# match forces cosmopolitan regardless of GBIF facet noise — these are the
# "common molds" the critique flagged: location is unknowable from the disease.
GENERALIST_GENERA = {
    "rhizopus", "botrytis", "aspergillus", "penicillium", "mucor",
    "cladosporium", "rhizoctonia", "sclerotinia", "sclerotium", "athelia",
    "fusarium", "pythium", "alternaria", "phoma", "geotrichum",
}
# Specific binomials that are cosmopolitan even if the genus has localized members.
GENERALIST_SPECIES = {
    "rhizoctonia solani", "sclerotinia sclerotiorum", "athelia rolfsii",
    "botrytis cinerea", "rhizopus stolonifer",
}


def _genus(name: str) -> str:
    return (name or "").strip().split()[0].lower() if name else ""


def load_ranges(path: str = DEFAULT_RANGES) -> dict:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} not found — run scripts/fetch_gbif_ranges.py first.")
    return json.load(open(path))


def _effective_countries(rec: dict):
    countries = rec.get("countries", {}) or {}
    total = max(1, rec.get("total", 0))
    eff = [c for c, n in countries.items()
           if n >= MIN_CTRY_RECORDS and (n / total) >= MIN_SHARE]
    return eff


def classify(name: str, ranges: dict) -> dict:
    """Return the geo-informativeness verdict for one pathogen Scientific Name."""
    rec = ranges.get(name, {}) or {}
    genus = _genus(name)
    total = rec.get("total", 0)
    status = rec.get("status")
    match = rec.get("matchType")
    countries = rec.get("countries", {}) or {}
    continents = {c: n for c, n in (rec.get("continents", {}) or {}).items()
                  if n >= MIN_CTRY_RECORDS}
    us_states = {s: n for s, n in (rec.get("us_states", {}) or {}).items()
                 if s and s.lower() != "n/a"}
    eff = _effective_countries(rec)
    n_eff, n_cont = len(eff), len(continents)

    out = {
        "pathogen": name, "gbif_key": rec.get("usageKey"),
        "match_type": match, "total_records": total,
        "n_countries": len(countries), "eff_countries": n_eff,
        "n_continents": n_cont, "n_us_states": len(us_states),
        "top_countries": sorted(countries.items(), key=lambda kv: -kv[1])[:8],
    }

    # 1) named generalist -> cosmopolitan (overrides facet noise)
    if name.strip().lower() in GENERALIST_SPECIES or genus in GENERALIST_GENERA:
        out.update(restriction_class="cosmopolitan",
                   reason=f"named ubiquitous generalist ('{genus}'); location not "
                          f"inferable from the disease")
        return out

    # 2) untrustworthy range estimate -> data_poor (honest abstention)
    if status != "ok" or not rec.get("usageKey") or match in (None, "NONE"):
        out.update(restriction_class="data_poor",
                   reason=f"no reliable GBIF backbone match (matchType={match})")
        return out
    if match == "HIGHERRANK" or (rec.get("rank") and
                                 rec["rank"] not in ("SPECIES", "SUBSPECIES",
                                                     "VARIETY", "FORM")):
        out.update(restriction_class="data_poor",
                   reason=f"GBIF match only at {rec.get('rank')} rank — range "
                          f"too coarse to trust")
        return out
    if total < MIN_RECORDS:
        out.update(restriction_class="data_poor",
                   reason=f"only {total} GBIF records (< {MIN_RECORDS}); a narrow "
                          f"footprint here may be sampling bias, not true range")
        return out

    # 3) genuine spread classification
    if n_eff >= COSMO_MIN_CTRY or n_cont >= COSMO_MIN_CONT:
        out.update(restriction_class="cosmopolitan",
                   reason=f"present in {n_eff} countries / {n_cont} continents "
                          f"(>= cosmopolitan threshold)")
    elif n_eff <= LOCALIZED_MAX_CTRY and n_cont <= LOCALIZED_MAX_CONT:
        out.update(restriction_class="localized",
                   reason=f"restricted to {n_eff} countries / {n_cont} continents")
    else:
        out.update(restriction_class="regional",
                   reason=f"intermediate spread: {n_eff} countries / {n_cont} "
                          f"continents (localizable only at coarse tier)")
    return out


def classify_all(ranges: dict) -> dict:
    return {name: classify(name, ranges) for name in ranges}


# localizable = we can honestly ask for a range; otherwise -> indeterminate gold
LOCALIZABLE = {"localized", "regional"}


def is_localizable(verdict: dict) -> bool:
    return verdict.get("restriction_class") in LOCALIZABLE


if __name__ == "__main__":  # quick distribution report
    import collections
    import sys
    rng = load_ranges(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_RANGES)
    verdicts = classify_all(rng)
    dist = collections.Counter(v["restriction_class"] for v in verdicts.values())
    print("restriction-class distribution over", len(verdicts), "pathogens:")
    for k, n in dist.most_common():
        print(f"  {k:13s} {n}")
    print("\nexamples per class:")
    for cls in ("localized", "regional", "cosmopolitan", "data_poor"):
        ex = [v for v in verdicts.values() if v["restriction_class"] == cls][:4]
        for v in ex:
            print(f"  [{cls}] {v['pathogen']:38s} "
                  f"eff_ctry={v['eff_countries']} cont={v['n_continents']} "
                  f"rec={v['total_records']}")
