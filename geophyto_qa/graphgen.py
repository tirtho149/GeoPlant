"""
geophyto_qa.graphgen
===================
Generate a **discriminator decision graph** for a mined look-alike pair with an
LLM, then validate it (the "LLM-generate + I validate" path).

This module is deliberately model-agnostic. It produces:
  * ``GRAPH_JSON_SCHEMA``       — the StructuredOutput schema (re-exported)
  * ``build_prompt(pair)``      — the few-shot prompt (gold graphs as exemplars)
  * ``load_gold() / load_generated()`` — graph stores keyed by pair_id
  * ``save_generated(pair_id, graph)``

The actual generation is done by whatever LLM you wire up. Two supported paths:

  A. Workflow fan-out (recommended for the full sweep): one agent per pair,
     ``agent(build_prompt(pair), schema=GRAPH_JSON_SCHEMA)`` — the schema forces
     valid JSON; write each result with ``save_generated``.

  B. Single-process API loop: implement ``call_llm`` below against your endpoint.

Either way, ``validate_graph`` is the gate before a graph enters the dataset.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from geophyto_qa.schema import GRAPH_JSON_SCHEMA, validate_graph  # noqa: F401  (re-export)

HERE = os.path.dirname(os.path.abspath(__file__))
GOLD_DIR = os.path.join(HERE, "graphs", "gold")
GEN_DIR = os.path.join(HERE, "graphs", "generated")


# --------------------------------------------------------------------------- #
# Graph stores
# --------------------------------------------------------------------------- #
def load_gold() -> List[Dict[str, Any]]:
    out = []
    for fn in sorted(os.listdir(GOLD_DIR)):
        if fn.endswith(".json"):
            out.append(json.load(open(os.path.join(GOLD_DIR, fn))))
    return out


def load_generated() -> Dict[str, Dict[str, Any]]:
    out = {}
    if not os.path.isdir(GEN_DIR):
        return out
    for fn in sorted(os.listdir(GEN_DIR)):
        if fn.endswith(".json"):
            rec = json.load(open(os.path.join(GEN_DIR, fn)))
            out[rec["pair_id"]] = rec
    return out


def save_generated(pair_id: str, kind: str, crop: str,
                   member_a: str, member_b: str, graph: Dict[str, Any],
                   source: str = "llm-generated") -> str:
    os.makedirs(GEN_DIR, exist_ok=True)
    rec = {"pair_id": pair_id, "kind": kind, "crop": crop,
           "member_a_label": member_a, "member_b_label": member_b,
           "source": source, "graph": graph}
    path = os.path.join(GEN_DIR, pair_id + ".json")
    with open(path, "w") as fh:
        json.dump(rec, fh, indent=2)
    return path


# --------------------------------------------------------------------------- #
# Prompt
# --------------------------------------------------------------------------- #
_SYSTEM = """You are a US extension plant pathologist building a diagnostic \
decision graph that lets an expert tell apart two LOOK-ALIKE plant diseases that \
appear on the same crop. Field experts confuse these because their visible \
presentation overlaps; your graph encodes how an expert actually separates them.

Branch ONLY on observable, agronomically real evidence, using these axes:
  - growth_stage : timing in the season / field history
  - plant_part   : which organ is affected (leaf, stem, root, crown, fruit, whole)
  - symptom_class: leaf spot / blight / chlorosis / canker / rot / wilt / mosaic
  - progression  : direction & pattern of spread (lower vs upper canopy, roots-up,
                   field distribution)
  - sign_vector  : pathogen signs (pustules, spore masses, mycelium, cysts, ooze)
                   or a vector
  - environment  : weather / soil / moisture conditions that favor one member
  - morphology   : fine structural detail (only if it discriminates)
  - habit        : overall appearance/size (weak, supporting only)

Rules:
  - 3 to 7 forks, ordered coarse -> fine.
  - EXACTLY ONE fork has weight "decisive": the single observation that, on its
    own, resolves the pair (the "force this step" fork, e.g. split the stem,
    flip the leaf, wash the roots). The rest are "supporting" or "weak".
  - a_signal always describes member_a; b_signal always describes member_b.
  - If the two are NOT genuinely confused in the field, set confusable=false and
    explain why; the pair will be dropped.
  - geo_localizable_<x> = true only if that disease's likelihood truly depends on
    US region/season; false if it occurs nationwide (cosmopolitan).
Return ONLY the JSON object for the schema. Do not invent evidence you are unsure
of; prefer fewer, certain forks."""


def _exemplar_block() -> str:
    """Render the gold graphs as compact few-shot exemplars."""
    chunks = []
    for rec in load_gold():
        g = rec["graph"]
        forks = "\n".join(
            f'    - [{fk["weight"]}/{fk["axis"]}] {fk["question"]} '
            f'| A({rec["member_a_label"]}): {fk["a_signal"]} '
            f'| B({rec["member_b_label"]}): {fk["b_signal"]}'
            for fk in g["forks"])
        chunks.append(
            f'### EXAMPLE ({rec["kind"]}) — {rec["member_a_label"]} (A) vs '
            f'{rec["member_b_label"]} (B), crop: {rec["crop"]}\n'
            f'shared look: {g["shared_presentation"]}\n'
            f'forks:\n{forks}\n'
            f'decisive fork resolves it; narrative_A: {g["narrative_a"]}')
    return "\n\n".join(chunks)


def build_prompt(pair: Dict[str, Any]) -> str:
    """Build the generation prompt for one mined candidate pair."""
    ma, mb = pair["member_a"], pair["member_b"]
    ctx = (
        f'CROP: {pair["crop"]}\n'
        f'MEMBER_A: {ma["disease"]}  '
        f'(scientific: {ma.get("path_sci") or "n/a"}; class: {ma["pathogen_class"]}; '
        f'{ma["n_imgs"]} images; descriptors: '
        f'{", ".join(d for d, _ in ma["descriptors"])})\n'
        f'MEMBER_B: {mb["disease"]}  '
        f'(scientific: {mb.get("path_sci") or "n/a"}; class: {mb["pathogen_class"]}; '
        f'{mb["n_imgs"]} images; descriptors: '
        f'{", ".join(d for d, _ in mb["descriptors"])})\n'
        f'CORPUS NOTE: both are recorded on {pair["crop"]} in US states '
        f'{", ".join(pair["shared_regions"]) or "(little overlap)"}; '
        f'shared image descriptors: {", ".join(pair["shared_descriptors"]) or "none"}.'
    )
    return (
        f"{_SYSTEM}\n\n"
        f"Here are validated exemplars of the format and quality expected:\n\n"
        f"{_exemplar_block()}\n\n"
        f"=== NOW BUILD THE GRAPH FOR THIS PAIR ===\n{ctx}\n\n"
        f"member_a is {ma['disease']}; member_b is {mb['disease']}. "
        f"Produce the JSON object only."
    )


# --------------------------------------------------------------------------- #
# Optional single-process generation (path B). Stub by default.
# --------------------------------------------------------------------------- #
def call_llm(prompt: str) -> Optional[Dict[str, Any]]:  # pragma: no cover
    """Wire this to your endpoint (vLLM / Anthropic / OpenAI). Must return a dict
    matching GRAPH_JSON_SCHEMA. Returns None if unavailable."""
    raise NotImplementedError(
        "Wire call_llm to an LLM, or use the Workflow fan-out path with "
        "agent(build_prompt(pair), schema=GRAPH_JSON_SCHEMA).")


def generate_and_save(pair: Dict[str, Any]) -> Optional[str]:
    """Path B helper: generate one graph via call_llm, validate, save."""
    graph = call_llm(build_prompt(pair))
    if graph is None:
        return None
    errs = validate_graph(graph)
    if errs:
        raise ValueError(f"{pair['pair_id']}: invalid graph: {errs}")
    return save_generated(pair["pair_id"], "disease", pair["crop"],
                          pair["member_a"]["disease"], pair["member_b"]["disease"], graph)
