"""
geophyto_qa.geo_oracle
=====================
The **contributor-de-biased geographic oracle** the design doc calls for.

Bugwood geography is biased by who uploaded: a single prolific photographer in
one state can make a cosmopolitan disease look state-specific. We de-bias by
counting **distinct contributors** (photographer ∪ organization) per
(disease, state) rather than raw images, then aggregate to US Census regions.

From that de-biased prior the oracle decides, per disease:
  * ``localizability`` ∈ {localizable, regional, cosmopolitan}
      - localizable : concentrated in 1-2 regions (geography is decisive)
      - regional    : a clear lean but present elsewhere
      - cosmopolitan: spread across the country (geography ~uninformative)
  * ``plausible_regions`` : the regions that carry the disease
  * ``local_pressure(state)`` : a phrase for how active the disease is where the
    farmer is, used verbatim in the dialogue.

Everything is computed from the **TRAIN split only** (anti-recall), exactly like
the geo prior in build_geo_vqa.py.
"""
from __future__ import annotations

import collections
from typing import Dict, List

from geophyto_qa.regions import region_of, division_of

# Localizability thresholds over the de-biased region distribution.
_LOCALIZABLE_MAX_REGIONS = 2          # in <=2 regions -> localizable
_LOCALIZABLE_MIN_TOPSHARE = 0.60      # or one region holds >=60%
_COSMO_MIN_REGIONS = 4               # in >=4 regions ...
_COSMO_MAX_TOPSHARE = 0.45           # ... and no region dominates -> cosmopolitan
ALL_REGIONS = ["Northeast", "Midwest", "South", "West"]


class GeoOracle:
    def __init__(self, train_rows: List[dict]):
        # distinct contributors per (disease, state)
        contrib = collections.defaultdict(lambda: collections.defaultdict(set))
        for r in train_rows:
            who = (r.get("photographer") or "").strip() or (r.get("org") or "").strip() or r.get("img", "")
            contrib[r["disease"]][r["state"]].add(who)
        # de-biased weight = #distinct contributors
        self.state_w: Dict[str, collections.Counter] = {}
        self.region_w: Dict[str, collections.Counter] = {}
        for dis, by_state in contrib.items():
            sw = collections.Counter({s: len(c) for s, c in by_state.items()})
            rw = collections.Counter()
            for s, w in sw.items():
                reg = region_of(s)
                if reg:
                    rw[reg] += w
            self.state_w[dis] = sw
            self.region_w[dis] = rw

    # --------------------------------------------------------------------- #
    def localizability(self, disease: str) -> str:
        rw = self.region_w.get(disease)
        if not rw:
            return "regional"
        total = sum(rw.values())
        n_reg = len(rw)
        top_share = max(rw.values()) / total if total else 0.0
        if n_reg <= _LOCALIZABLE_MAX_REGIONS or top_share >= _LOCALIZABLE_MIN_TOPSHARE:
            return "localizable"
        if n_reg >= _COSMO_MIN_REGIONS and top_share < _COSMO_MAX_TOPSHARE:
            return "cosmopolitan"
        return "regional"

    def is_localizable(self, disease: str, graph_flag: bool | None = None) -> bool:
        """Effective localizability for the counterfactual swap.

        The empirical de-biased oracle is authoritative; the LLM graph flag, when
        provided, can only *promote* a regional/cosmopolitan call to localizable
        (agronomic knowledge the sparse corpus may miss), never demote.
        """
        cls = self.localizability(disease)
        emp = cls in ("localizable", "regional")
        return bool(emp or graph_flag)

    def plausible_regions(self, disease: str) -> List[str]:
        rw = self.region_w.get(disease)
        if not rw:
            return []
        total = sum(rw.values())
        # keep regions holding >=15% of de-biased weight, always >=1.
        keep = [reg for reg, w in rw.most_common() if w / total >= 0.15]
        return keep or [rw.most_common(1)[0][0]]

    def geo_informative(self, disease: str) -> bool:
        """True when the de-biased corpus actually carries a regional signal for
        this disease (localizable or regional) — i.e. geography can score the
        counterfactual swap. Cosmopolitan diseases are not informative."""
        return self.localizability(disease) in ("localizable", "regional")

    def local_pressure(self, disease: str, state: str) -> str:
        """A clean, self-contained clause describing how active `disease` is
        where the farmer is. Region-bearing unless the disease is cosmopolitan."""
        reg = region_of(state)
        plaus = self.plausible_regions(disease)
        cls = self.localizability(disease)
        if cls == "cosmopolitan":
            return f"{disease} occurs across US regions, so location alone is not decisive"
        if reg in plaus:
            return f"{disease} is well established in the {reg} this season"
        return (f"{disease} is uncommon in the {reg}, "
                f"which concentrates in the {', '.join(plaus)}")

    def swap_targets(self, disease: str, true_state: str):
        """Pick a (state, region) where this disease is *implausible* — used to
        build the counterfactual region swap. Returns (state, region) or None."""
        plaus = set(self.plausible_regions(disease))
        # prefer a region with no recorded contributors for this disease
        rw = self.region_w.get(disease, {})
        rep_state = {"Northeast": "Maine", "Midwest": "Iowa",
                     "South": "Louisiana", "West": "Colorado"}
        for reg in ALL_REGIONS:
            if reg not in plaus and rw.get(reg, 0) == 0:
                rep = rep_state[reg]
                if rep != true_state:
                    return rep, reg
        return None

    def least_plausible_region(self, disease: str, exclude: str | None = None):
        """Fallback swap target: the region with the LOWEST de-biased weight for
        this disease (the least likely place to find it), excluding `exclude`.
        Returns (rep_state, region). Used when no zero-weight region exists."""
        rep_state = {"Northeast": "Maine", "Midwest": "Iowa",
                     "South": "Louisiana", "West": "Colorado"}
        rw = self.region_w.get(disease, {})
        ranked = sorted(ALL_REGIONS, key=lambda r: (rw.get(r, 0), r))
        for reg in ranked:
            if reg != exclude:
                return rep_state[reg], reg
        reg = ranked[0]
        return rep_state[reg], reg

    def swap_to_distractor_region(self, true_disease: str, distractor: str,
                                  exclude: str | None = None):
        """Counterfactual target for Lane B: a region where the DISTRACTOR is
        genuinely *more* plausible than the true member (per the de-biased prior).

        The old `least_plausible_region(true)` only demoted the true member and
        never checked the distractor was plausible there — so "flip toward the
        distractor" could land in a region where the distractor is *also*
        implausible (an invalid control). This returns (state, region) only when
        some region actually favors the distractor, else None (caller should then
        treat the item as a no-flip control)."""
        rep_state = {"Northeast": "Maine", "Midwest": "Iowa",
                     "South": "Louisiana", "West": "Colorado"}
        twt = self.region_w.get(true_disease, {})
        dwt = self.region_w.get(distractor, {})
        cands = [r for r in ALL_REGIONS
                 if r != exclude and dwt.get(r, 0) > 0 and dwt.get(r, 0) > twt.get(r, 0)]
        if not cands:
            return None
        best = max(cands, key=lambda r: dwt.get(r, 0) - twt.get(r, 0))
        return rep_state[best], best

    def oracle_block(self, disease: str, state: str, graph_flag: bool | None = None) -> dict:
        """The `geo_oracle` field for an item."""
        return {
            "plausible_regions": self.plausible_regions(disease),
            "localizability": self.localizability(disease),
            "geo_informative": self.geo_informative(disease),
            "effective_localizable": self.is_localizable(disease, graph_flag),
            "local_pressure": self.local_pressure(disease, state),
            "debiased_region_weights": dict(self.region_w.get(disease, {})),
            "source": "train-split-only, contributor-de-biased",
        }
