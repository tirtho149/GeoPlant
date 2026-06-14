"""
geophyto_qa.regions
===================
US Census region/division ladder, Köppen-major names, and pathogen-class
heuristics. Factored out of scripts/build_geo_vqa.py so the QA builder and the
geo-oracle share one source of truth for the admin1 -> division -> region
coarsening used in geography-aware reasoning.
"""
from __future__ import annotations

KOPPEN_MAJOR = {"A": "tropical", "B": "arid", "C": "temperate",
                "D": "continental", "E": "polar"}

# US Census division per contiguous-US state (+ DC).
CENSUS_DIVISION = {
    "Connecticut": "New England", "Maine": "New England", "Massachusetts": "New England",
    "New Hampshire": "New England", "Rhode Island": "New England", "Vermont": "New England",
    "New Jersey": "Mid-Atlantic", "New York": "Mid-Atlantic", "Pennsylvania": "Mid-Atlantic",
    "Illinois": "East North Central", "Indiana": "East North Central", "Michigan": "East North Central",
    "Ohio": "East North Central", "Wisconsin": "East North Central",
    "Iowa": "West North Central", "Kansas": "West North Central", "Minnesota": "West North Central",
    "Missouri": "West North Central", "Nebraska": "West North Central",
    "North Dakota": "West North Central", "South Dakota": "West North Central",
    "Delaware": "South Atlantic", "District of Columbia": "South Atlantic", "Florida": "South Atlantic",
    "Georgia": "South Atlantic", "Maryland": "South Atlantic", "North Carolina": "South Atlantic",
    "South Carolina": "South Atlantic", "Virginia": "South Atlantic", "West Virginia": "South Atlantic",
    "Alabama": "East South Central", "Kentucky": "East South Central",
    "Mississippi": "East South Central", "Tennessee": "East South Central",
    "Arkansas": "West South Central", "Louisiana": "West South Central",
    "Oklahoma": "West South Central", "Texas": "West South Central",
    "Arizona": "Mountain", "Colorado": "Mountain", "Idaho": "Mountain", "Montana": "Mountain",
    "Nevada": "Mountain", "New Mexico": "Mountain", "Utah": "Mountain", "Wyoming": "Mountain",
    "Alaska": "Pacific", "California": "Pacific", "Hawaii": "Pacific",
    "Oregon": "Pacific", "Washington": "Pacific",
}
DIVISION_REGION = {
    "New England": "Northeast", "Mid-Atlantic": "Northeast",
    "East North Central": "Midwest", "West North Central": "Midwest",
    "South Atlantic": "South", "East South Central": "South", "West South Central": "South",
    "Mountain": "West", "Pacific": "West",
}


def region_of(state):
    div = CENSUS_DIVISION.get(state)
    return DIVISION_REGION.get(div) if div else None


def division_of(state):
    return CENSUS_DIVISION.get(state)


def pathogen_class(name: str) -> str:
    n = (name or "").lower()
    if "virus" in n or "viroid" in n:
        return "viral"
    if "phytoplasma" in n:
        return "phytoplasma"
    if any(k in n for k in ("bacterial", "xanthomonas", "pseudomonas", "erwinia", "ralstonia")):
        return "bacterial"
    if "nematode" in n or "cyst" in n:
        return "nematode"
    return "fungal/oomycete"
