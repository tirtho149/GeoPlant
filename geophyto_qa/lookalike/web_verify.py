"""
geophyto_qa.lookalike.web_verify
===============================
Level-2 (label) look-alike test. A pair is admitted only if a credible web
source states the two diseases are confused / look alike. Each verified pair
stores a quoted snippet and the source URL, so every look-alike claim in the
dataset is auditable.

The search itself is run by an LLM/agent with web tools (WebSearch/WebFetch) — it
is not hard-coded here because judging source credibility and extracting the
right quote is a reasoning task. This module only defines the evidence record,
the store, and the credibility gate.

Evidence record (one per pair):
  {
    "pair_id", "crop", "member_a", "member_b",
    "verified": bool,
    "claim":   short paraphrase of why they are confused,
    "quote":   verbatim snippet from the source supporting confusion,
    "source_url", "source_title",
    "source_type": "extension" | "university" | "peer_reviewed" | "gov" | "other",
    "secondary_sources": [url, ...],
    "query": the search query used
  }

Credible source types (count toward verification):
  extension, university, peer_reviewed, gov.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(HERE, "web_evidence.json")

CREDIBLE_TYPES = {"extension", "university", "peer_reviewed", "gov"}
# domain hints used to auto-tag source_type when an agent does not set it.
_DOMAIN_TYPE = [
    ("extension.", "extension"), (".extension", "extension"),
    ("ces.ncsu", "extension"), ("ipm.", "extension"),
    ("plant-pest-advisory.rutgers", "extension"), ("vegetables.cornell", "extension"),
    (".edu", "university"),
    ("doi.org", "peer_reviewed"), ("ncbi.nlm.nih.gov", "peer_reviewed"),
    ("sciencedirect", "peer_reviewed"), ("apsnet.org", "peer_reviewed"),
    ("springer", "peer_reviewed"), ("mdpi.com", "peer_reviewed"),
    (".gov", "gov"), ("usda", "gov"),
]


def classify_source(url: str) -> str:
    u = (url or "").lower()
    for hint, typ in _DOMAIN_TYPE:
        if hint in u:
            return typ
    return "other"


def load_evidence() -> Dict[str, Dict[str, Any]]:
    if os.path.exists(STORE):
        return json.load(open(STORE))
    return {}


def save_evidence(ev: Dict[str, Dict[str, Any]]):
    with open(STORE, "w") as fh:
        json.dump(ev, fh, indent=2)


def record(pair_id: str, crop: str, member_a: str, member_b: str,
           quote: str, source_url: str, source_title: str = "",
           claim: str = "", source_type: str = "", query: str = "",
           secondary_sources: List[str] | None = None,
           verified: bool | None = None) -> Dict[str, Any]:
    """Add/replace one pair's web evidence and persist. Returns the record."""
    ev = load_evidence()
    stype = source_type or classify_source(source_url)
    rec = {
        "pair_id": pair_id, "crop": crop,
        "member_a": member_a, "member_b": member_b,
        "verified": (stype in CREDIBLE_TYPES and bool(quote)) if verified is None else verified,
        "claim": claim, "quote": quote,
        "source_url": source_url, "source_title": source_title,
        "source_type": stype,
        "secondary_sources": secondary_sources or [],
        "query": query,
    }
    ev[pair_id] = rec
    save_evidence(ev)
    return rec


def is_verified(pair_id: str) -> bool:
    return bool(load_evidence().get(pair_id, {}).get("verified"))
