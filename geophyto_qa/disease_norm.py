"""
geophyto_qa.disease_norm
=======================
Label hygiene for the scraped Bugwood NormDisease list:

  * clean_display(name)   -> drop author citations ("Sacc.", "Schwabe", ...),
                             "Genus " prefixes, and tidy whitespace.
  * organism(sci_name)    -> (genus, species) from the Scientific Name.
  * same_organism(a, b)   -> True when two members are the SAME organism
                             (same genus, and matching/absent species) — e.g.
                             Bread Mold (Rhizopus stolonifer) vs Rhizopus Soft
                             Rots (Rhizopus). Such pairs are a disease against
                             itself and must be dropped.
  * same_organism_drops(confirmed, sci_map) -> set of pair_ids to drop.
"""
from __future__ import annotations
import re
from typing import Dict, Set, Tuple

# Author-citation tokens that trail Bugwood scientific labels.
_AUTHORITIES = [
    "Sacc.", "Schwabe", "De Not.", "Ehrenb.", "Vuill.", "Fr.", "Pers.",
    "Cooke", "Berk.", "Curt.", "Wint.", "Sorauer", "L.", "DC.", "Mont.",
    "Verkley & U. Braun", "(Ehrenb.) Vuill.", "var. stolonifer",
]


def clean_display(name: str) -> str:
    s = (name or "").strip()
    s = re.sub(r"^Genus\s+", "", s)
    for a in sorted(_AUTHORITIES, key=len, reverse=True):
        s = s.replace(" " + a, "")
    # strip a trailing parenthetical authority e.g. "(Ehrenb.)"
    s = re.sub(r"\s*\([A-Z][^)]*\.\)\s*$", "", s)
    return re.sub(r"\s{2,}", " ", s).strip()


def organism(sci_name: str) -> Tuple[str, str]:
    toks = (sci_name or "").strip().split()
    genus = toks[0].lower() if toks else ""
    species = toks[1].lower() if len(toks) > 1 and toks[1][:1].islower() else ""
    return genus, species


# STRICT 1:1 teleomorph/anamorph synonyms — the SAME fungus under two genus
# names. Deliberately conservative: only pairs that are genuinely one organism,
# NOT loose form-genus complexes (e.g. Cercospora vs Ramularia are DISTINCT and
# are kept as real look-alikes).
_GENUS_ALIASES = [
    {"diaporthe", "phomopsis"},        # teleomorph / anamorph
    {"glomerella", "colletotrichum"},  # teleomorph / anamorph
]


def _alias_genus(g: str) -> str:
    for cl in _GENUS_ALIASES:
        if g in cl:
            return min(cl)
    return g


def _species_agree(sa: str, sb: str) -> bool:
    # absent on either side, exact match, or shared 5-char prefix (spelling
    # variants like juniperivora / juniperovora).
    if not sa or not sb:
        return True
    return sa == sb or sa[:5] == sb[:5]


def same_organism(a_sci: str, b_sci: str) -> bool:
    ga, sa = organism(a_sci)
    gb, sb = organism(b_sci)
    if not ga:
        return False
    if _alias_genus(ga) != _alias_genus(gb):
        return False
    # same genus (directly or via a strict anamorph/teleomorph alias) AND the
    # species epithets agree (or are absent) -> one organism.
    return _species_agree(sa, sb)


def build_sci_map(source: str = None) -> Dict[Tuple[str, str], str]:
    """(crop, disease) -> most common scientific name. Sourced from the active
    dataset via data_source; for an ImageFolder (no taxonomy) this is empty, so
    same-organism synonym dropping simply no-ops."""
    import collections
    from geophyto_qa.data_source import load_rows
    c = collections.defaultdict(collections.Counter)
    for r in load_rows(source):
        sci = (r.get("path_sci") or r.get("path_common") or "").strip()
        if sci:
            c[(r["crop"], r["disease"])][sci] += 1
    return {k: v.most_common(1)[0][0] for k, v in c.items() if v}


def same_organism_drops(confirmed: dict, sci_map: Dict[Tuple[str, str], str]) -> Set[str]:
    drops = set()
    for pid, d in confirmed.items():
        a = sci_map.get((d["crop"], d["member_a"]), "")
        b = sci_map.get((d["crop"], d["member_b"]), "")
        if same_organism(a, b):
            drops.add(pid)
    return drops
