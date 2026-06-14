"""
geoplant.geocode.county_centroids
=================================
Resolve a scraped Bugwood row to the best available (lat, lon) with an
explicit precision tag, using a priority ladder:

    1. point   — explicit Lat/Lon from the Bugwood API (rare, ~1%)
    2. county  — US Census county-centroid (when a county is known, ~5%)
    3. state   — US state population-weighted centroid (the common case)
    4. none    — unresolvable (foreign / blank)

The county centroids come from the US Census 2023 Gazetteer
(data/2023_Gaz_counties_national.txt), no auth required.
"""

from __future__ import annotations

import csv
import os
import re
from functools import lru_cache
from typing import Dict, Optional, Tuple

from utils.geo import US_STATE_CENTROID, state_to_latlon

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "data")
GAZ = os.path.join(DATA, "2023_Gaz_counties_national.txt")

STATE_NAME_TO_ABBR = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "district of columbia": "DC", "florida": "FL", "georgia": "GA", "hawaii": "HI",
    "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI",
    "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX",
    "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY", "puerto rico": "PR",
}
_STATE_NAMES = set(US_STATE_CENTROID.keys())


@lru_cache(maxsize=1)
def _county_index() -> Dict[Tuple[str, str], Tuple[float, float]]:
    """{(state_abbr, county_name_lower) -> (lat, lon)} from the Census gazetteer."""
    idx: Dict[Tuple[str, str], Tuple[float, float]] = {}
    if not os.path.isfile(GAZ):
        return idx
    with open(GAZ, encoding="latin-1") as fh:
        rd = csv.reader(fh, delimiter="\t")
        header = [h.strip() for h in next(rd)]  # Census headers carry trailing spaces
        col = {name: i for i, name in enumerate(header)}
        for parts in rd:
            if len(parts) < len(header):
                continue
            usps = parts[col["USPS"]].strip()
            name = re.sub(r"\s+(County|Parish|Borough|Census Area|Municipio)$", "",
                          parts[col["NAME"]].strip(), flags=re.I).strip().lower()
            try:
                lat = float(parts[col["INTPTLAT"]].strip())
                lon = float(parts[col["INTPTLONG"]].strip())
            except (TypeError, ValueError, IndexError):
                continue
            if usps and name:
                idx[(usps, name)] = (lat, lon)
    return idx


def _find_state(*candidates: str) -> str:
    """Return canonical lowercase state name found among candidate strings."""
    for c in candidates:
        key = (c or "").strip().lower()
        if key in _STATE_NAMES:
            return key
    return ""


def resolve_point(row: dict) -> Tuple[Optional[float], Optional[float], str, str]:
    """Resolve a row -> (lat, lon, precision, source).

    precision in {"point","county","state","none"}.
    """
    # 1. explicit point coordinates
    try:
        lat = float(row.get("Lat") or "")
        lon = float(row.get("Lon") or "")
        if lat and lon:
            return lat, lon, "point", "bugwood_latlon"
    except (TypeError, ValueError):
        pass

    # Identify the state from the dedicated column, the Location string parts,
    # or the legacy single "Location" state value.
    loc = row.get("Location", "") or ""
    parts = [p.strip() for p in loc.split(",")]
    state = _find_state(row.get("State", ""), *parts, row.get("Location", ""))

    # 2. county centroid
    county = (row.get("County") or "").strip().lower()
    county = re.sub(r"\s+(county|parish|borough)$", "", county, flags=re.I).strip()
    if not county:
        # try to recover a county from a "... County" location part
        for p in parts:
            if re.search(r"\bcounty\b", p, re.I):
                county = re.sub(r"\s+county$", "", p.strip(), flags=re.I).lower()
                break
    if state and county:
        abbr = STATE_NAME_TO_ABBR.get(state, "")
        hit = _county_index().get((abbr, county))
        if hit:
            return hit[0], hit[1], "county", "census_county_centroid"

    # 3. state centroid
    if state:
        slat, slon = state_to_latlon(state)
        if slat is not None:
            return slat, slon, "state", "state_centroid"

    # 4. unresolved
    return None, None, "none", ""
