"""
geophyto_qa.schema
==================
Two schemas:

1. The **discriminator decision graph** — the expert's look-alike CoT, encoded
   from the docx flow. A graph distinguishes ONE confusable pair (member_a vs
   member_b) through an ordered list of *forks*. Each fork branches on one of
   the axes the docx / user spelled out for disease reasoning:

       host + plant_part + growth_stage + symptom_class + progression
            + sign_vector + environment   (+ morphology / habit for weeds/insects)

   Exactly one fork is flagged `decisive` (the docx "force stem-splitting step"):
   the single observation that, on its own, resolves the pair.

2. The **dialogue item** — one output record: a real Bugwood image + a
   multi-turn, geography-aware farmer<->expert dialogue that *walks* the graph,
   plus gold answers, scoring flags, and the counterfactual region swap.

`GRAPH_JSON_SCHEMA` is the JSON Schema handed to an LLM (StructuredOutput) to
generate a graph for a mined pair; `validate_graph` is the I-validate gate.
"""
from __future__ import annotations

from typing import Any, Dict, List

# Axes a fork may branch on. Diseases lean on the first six; weeds/insects also
# use morphology/habit. Kept as a closed set so the self-check can audit graphs.
FORK_AXES = [
    "growth_stage",   # seedling vs reproductive timing / field history
    "plant_part",     # which organ is affected (leaf / stem / root / fruit / whole)
    "symptom_class",  # leaf spot / blight / chlorosis / canker / rot / wilt
    "progression",    # direction of spread (roots-up vs top-down; lower vs upper canopy)
    "sign_vector",    # pathogen signs (pustules, cysts, spore masses) or the insect/vector itself
    "environment",    # soil / weather / season conditions that favor one member
    "morphology",     # fine structural traits (leaf shape, petiole, bracts, leg/stripe — weeds/insects)
    "habit",          # overall plant/insect habit & size
]
GRAPH_KINDS = ["disease", "weed", "insect"]
FORK_WEIGHTS = ["weak", "supporting", "decisive"]


# --------------------------------------------------------------------------- #
# JSON Schema for LLM graph generation (StructuredOutput-compatible)
# --------------------------------------------------------------------------- #
GRAPH_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "confusable", "confusable_reason", "shared_presentation",
        "forks", "narrative_a", "narrative_b",
        "management_a", "management_b",
        "geo_localizable_a", "geo_localizable_b",
    ],
    "properties": {
        "confusable": {
            "type": "boolean",
            "description": "True if the two members are genuinely confused in the field. "
                           "If false, the pair is dropped from the dataset.",
        },
        "confusable_reason": {
            "type": "string",
            "description": "One sentence: why they are (or are not) look-alikes.",
        },
        "shared_presentation": {
            "type": "string",
            "description": "The overlapping appearance that makes them hard to tell apart.",
        },
        "forks": {
            "type": "array",
            "minItems": 3,
            "maxItems": 7,
            "description": "Ordered diagnostic forks the expert walks, coarse -> decisive. "
                           "Exactly one fork must have weight 'decisive'.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["axis", "question", "a_signal", "b_signal", "weight"],
                "properties": {
                    "axis": {"type": "string", "enum": FORK_AXES},
                    "question": {
                        "type": "string",
                        "description": "The diagnostic question the expert asks/checks at this fork.",
                    },
                    "a_signal": {
                        "type": "string",
                        "description": "Observation that leans toward member_a (the FIRST member).",
                    },
                    "b_signal": {
                        "type": "string",
                        "description": "Observation that leans toward member_b (the SECOND member).",
                    },
                    "weight": {"type": "string", "enum": FORK_WEIGHTS},
                },
            },
        },
        "narrative_a": {
            "type": "string",
            "description": "One-sentence CoT conclusion if the evidence points to member_a "
                           "(\"Because ... I classify this as A rather than B.\").",
        },
        "narrative_b": {
            "type": "string",
            "description": "One-sentence CoT conclusion if the evidence points to member_b.",
        },
        "management_a": {"type": "string", "description": "Short management action if it is member_a."},
        "management_b": {"type": "string", "description": "Short management action if it is member_b."},
        "geo_localizable_a": {
            "type": "boolean",
            "description": "True if member_a's likelihood depends on US region/season "
                           "(localizable); false if cosmopolitan (everywhere).",
        },
        "geo_localizable_b": {"type": "boolean", "description": "Same, for member_b."},
    },
}


# --------------------------------------------------------------------------- #
# Validation (the "I validate" gate over LLM output)
# --------------------------------------------------------------------------- #
def validate_graph(g: Dict[str, Any]) -> List[str]:
    """Return a list of problems; empty list == valid."""
    errs: List[str] = []
    if not isinstance(g, dict):
        return ["graph is not an object"]

    for key in GRAPH_JSON_SCHEMA["required"]:
        if key not in g:
            errs.append(f"missing key: {key}")
    if errs:
        return errs

    if not isinstance(g["confusable"], bool):
        errs.append("confusable must be bool")
    # A non-confusable pair is intentionally allowed (it gets dropped upstream),
    # but it still must carry a reason.
    if not str(g.get("confusable_reason", "")).strip():
        errs.append("confusable_reason empty")

    forks = g.get("forks")
    if not isinstance(forks, list) or not (3 <= len(forks) <= 7):
        errs.append("forks must be a list of 3..7 items")
        forks = []
    decisive = 0
    for j, fk in enumerate(forks):
        if not isinstance(fk, dict):
            errs.append(f"fork[{j}] not an object"); continue
        if fk.get("axis") not in FORK_AXES:
            errs.append(f"fork[{j}].axis invalid: {fk.get('axis')!r}")
        if fk.get("weight") not in FORK_WEIGHTS:
            errs.append(f"fork[{j}].weight invalid: {fk.get('weight')!r}")
        for f in ("question", "a_signal", "b_signal"):
            if not str(fk.get(f, "")).strip():
                errs.append(f"fork[{j}].{f} empty")
        if fk.get("weight") == "decisive":
            decisive += 1
    if g.get("confusable") and decisive != 1:
        errs.append(f"need exactly 1 decisive fork, found {decisive}")

    for b in ("geo_localizable_a", "geo_localizable_b"):
        if not isinstance(g.get(b), bool):
            errs.append(f"{b} must be bool")
    return errs


def decisive_fork(g: Dict[str, Any]) -> Dict[str, Any] | None:
    for fk in g.get("forks", []):
        if fk.get("weight") == "decisive":
            return fk
    return None
