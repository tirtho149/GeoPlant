"""
geophyto_qa.render_dialogue
==========================
Deterministic renderer: walk a discriminator decision graph for ONE real
Bugwood image (whose true label is one member of the pair) into a multi-turn,
geography-aware farmer<->expert dialogue, plus gold answers, scoring flags, the
decision-graph CoT, and the counterfactual region swap.

No LLM at this stage — everything is templated from the validated graph + the
image's geo facts + the contributor-de-biased oracle, so the build is fully
reproducible and self-checkable (matching the design doc §1, §4, §5).

The expert's reasoning is geography-aware: the farmer reports their location at
turn F2, and the expert *uses* it at E2/E3 (long-context integration). The
distractor member is explicitly ruled out via the decisive fork (VQA grounding).
"""
from __future__ import annotations

import random
from typing import Any, Dict, List

from geophyto_qa.regions import region_of, division_of, KOPPEN_MAJOR

DESCRIPTOR_PART = {
    "Symptoms": "leaves", "Sign": "leaves", "Foliage": "foliage",
    "Fruit(s)": "fruit", "Fruiting Bodies": "tissue", "Asexual Spore": "leaves",
    "Sexual Spore": "tissue", "Stem(s)": "stems", "Plant(s)": "plants",
    "Seedling(s)": "seedlings", "Research": "plant",
}


def _part(descriptor: str) -> str:
    return DESCRIPTOR_PART.get(descriptor, "plants")


def _lc_first(s: str) -> str:
    return s[:1].lower() + s[1:] if s else s


def _strip_period(s: str) -> str:
    return s.rstrip(". ").strip()


def _pick_forks(graph: Dict[str, Any]):
    """Decisive fork + the strongest supporting fork (distinct axis)."""
    forks = graph["forks"]
    decisive = next(fk for fk in forks if fk["weight"] == "decisive")
    supporting = [fk for fk in forks
                  if fk is not decisive and fk["weight"] == "supporting"]
    support = supporting[0] if supporting else next(
        (fk for fk in forks if fk is not decisive), decisive)
    return decisive, support


def render_item(rec: Dict[str, Any], graph: Dict[str, Any], img: Dict[str, Any],
                true_member: str, oracle, split: str, seed_salt: int) -> Dict[str, Any]:
    """Build one dialogue item.

    rec         : the graph record (member_a_label, member_b_label, crop, kind)
    graph       : rec['graph'] (validated)
    img         : the Bugwood image row (state, descriptor, host, url, ...)
    true_member : 'a' or 'b' — which member this image actually is
    oracle      : GeoOracle (TRAIN-only)
    """
    rng = random.Random(f"{img['img']}|{seed_salt}")
    a_lab, b_lab = rec["member_a_label"], rec["member_b_label"]
    true_lab = a_lab if true_member == "a" else b_lab
    dist_lab = b_lab if true_member == "a" else a_lab
    geo_flag = graph["geo_localizable_a"] if true_member == "a" else graph["geo_localizable_b"]

    def true_sig(fk):  return fk["a_signal"] if true_member == "a" else fk["b_signal"]
    def dist_sig(fk):  return fk["a_signal"] if true_member == "b" else fk["b_signal"]
    mgmt = graph["management_a"] if true_member == "a" else graph["management_b"]
    narrative = graph["narrative_a"] if true_member == "a" else graph["narrative_b"]

    decisive, support = _pick_forks(graph)
    state = img["state"]; region = region_of(state)
    part = _part(img.get("descriptor", "Symptoms"))
    host = img.get("host_common") or rec["crop"]
    pressure = oracle.local_pressure(true_lab, state)
    plausible = oracle.plausible_regions(true_lab)
    cls = oracle.localizability(true_lab)
    # `geo_informative`: the de-biased corpus carries a regional signal, so the
    # expert can (and must) use location and the counterfactual swap can score.
    geo_informative = oracle.geo_informative(true_lab)
    in_plausible = region in plausible

    # ---- dialogue (4 farmer turns / 4 expert turns) --------------------- #
    F1 = (f"My {host} {part} show {_lc_first(_strip_period(graph['shared_presentation']))}. "
          f"What is this?")
    E1 = (f"That look can be more than one thing. {decisive['question']} "
          f"Also, where are you farming, and {_lc_first(support['question'])}")
    F2 = (f"{_strip_period(true_sig(decisive))}. I'm in {state}. "
          f"{_strip_period(true_sig(support))}.")
    E2 = (f"The {_lc_first(_strip_period(true_sig(decisive)))} points to {true_lab} "
          f"rather than {dist_lab}, which would instead show "
          f"{_lc_first(_strip_period(dist_sig(decisive)))}. "
          + (f"It also fits where you are: {_strip_period(pressure)}."
             if geo_informative else
             f"On geography, {_strip_period(pressure)}; I weigh the visible signs most."))
    F3 = "Will it spread, and what should I do about it?"
    E3 = (f"{_strip_period(mgmt)}. "
          + (f"And since {_lc_first(_strip_period(pressure))}, act promptly rather than waiting."
             if geo_informative and in_plausible else
             "Base your action on the signs and stage rather than location alone."))
    F4 = rng.choice([
        "My neighbor says it's just from the weather and nothing to worry about.",
        "Someone told me this always clears up on its own.",
        "A friend thinks it's just fertilizer burn.",
    ])
    E4 = (f"Weather can favor it, but that is not a reason to dismiss it: the "
          f"{_lc_first(_strip_period(true_sig(decisive)))} is what separates "
          f"{true_lab} from {dist_lab}, and "
          + (f"in your area {_lc_first(_strip_period(pressure))}."
             if geo_informative else
             "the diagnosis rests on those signs regardless of location."))

    dialogue = [
        {"turn": "F1", "speaker": "farmer", "text": F1, "has_image": True},
        {"turn": "E1", "speaker": "expert", "text": E1, "has_image": False},
        {"turn": "F2", "speaker": "farmer", "text": F2, "has_image": False},
        {"turn": "E2", "speaker": "expert", "text": E2, "has_image": False},
        {"turn": "F3", "speaker": "farmer", "text": F3, "has_image": False},
        {"turn": "E3", "speaker": "expert", "text": E3, "has_image": False},
        {"turn": "F4", "speaker": "farmer", "text": F4, "has_image": False},
        {"turn": "E4", "speaker": "expert", "text": E4, "has_image": False},
    ]

    # ---- decision-graph CoT (the expert's grounded chain) --------------- #
    cot = [
        {"step": "PERCEIVE", "cites": "image (Descriptor Name)",
         "text": f"On the {host} {part} I see {_lc_first(_strip_period(graph['shared_presentation']))}, "
                 f"which {a_lab} and {b_lab} share."},
        {"step": f"FORK:{support['axis']}", "cites": f"farmer report ({support['axis']})",
         "text": f"{support['question']} Observed: {_strip_period(true_sig(support))} "
                 f"-> leans {true_lab}."},
        {"step": f"DECISIVE:{decisive['axis']}", "cites": f"image/farmer ({decisive['axis']})",
         "text": f"{decisive['question']} Observed: {_strip_period(true_sig(decisive))} "
                 f"-> {true_lab}; {dist_lab} would show {_lc_first(_strip_period(dist_sig(decisive)))}."},
        {"step": "GEO", "cites": "contributor-de-biased oracle (TRAIN only)",
         "text": (f"{pressure}; localizability={oracle.localizability(true_lab)}, "
                  f"plausible regions: {', '.join(plausible) or 'n/a'}.")},
        {"step": "CONCLUDE", "cites": "decision graph",
         "text": narrative},
    ]

    # ---- counterfactual region swap ------------------------------------- #
    # control item  <=>  geography is NOT informative (cosmopolitan): swapping the
    # stated location should NOT change the answer. For geo-informative diseases,
    # swap to the least-plausible region and expect the answer to shift.
    if geo_informative:
        swap_state, swap_region = (oracle.swap_targets(true_lab, state)
                                   or oracle.least_plausible_region(true_lab, exclude=region))
        counterfactual = {
            "control": False,
            "swap_location_to": swap_state,
            "swap_region": swap_region,
            "expected_shift": (f"{true_lab} demoted (uncommon in the {swap_region}); "
                               f"{dist_lab} or another cause promoted unless the decisive "
                               f"sign ({_lc_first(_strip_period(true_sig(decisive)))}) is still present."),
        }
    else:
        counterfactual = {
            "control": True,
            "swap_location_to": "Iowa" if state != "Iowa" else "Georgia",
            "swap_region": None,
            "expected_shift": (f"No change: {true_lab} is {cls} "
                               f"(geography is not decisive), so the answer should stay put."),
        }

    # ---- gold + scoring flags ------------------------------------------- #
    gold = {
        "diagnosis": true_lab,
        "ruled_out": dist_lab,
        "decisive_evidence": _strip_period(true_sig(decisive)),
        "management": _strip_period(mgmt),
        "geo_tier": {"state": state, "division": division_of(state),
                     "region": region, "country": "United States"},
        "answer_correct_ref": true_lab,
        "geographic_consistency_ref": {
            "geo_informative": geo_informative,
            "localizability": cls,
            "supports": in_plausible if geo_informative else None,
            "must_use_region": geo_informative,
        },
        "long_context_integration_ref": {
            "location_given_turn": "F2", "location_used_turns": ["E2", "E3", "E4"],
        },
        "vqa_grounding_ref": {
            "shared_sign": _strip_period(graph["shared_presentation"]),
            "decisive_sign": _strip_period(true_sig(decisive)),
        },
    }

    return {
        "item_id": f"gpqa-{img['img']}-{true_member}",
        "kind": rec.get("kind", "disease"),
        "image": {
            "url": img["url"], "image_number": img["img"],
            "attribution": img.get("cite", ""), "license_note": "per-image CC; see Bugwood record",
        },
        "lookalike": {
            "pair_id": rec["pair_id"], "crop": rec["crop"],
            "true": true_lab, "distractor": dist_lab,
            "shared_presentation": graph["shared_presentation"],
        },
        "grounding": {
            "host": host, "host_sci": img.get("host_sci", ""),
            "disease": true_lab, "pathogen_sci": img.get("path_sci", ""),
            "region": region, "state": state,
            "koppen_major": KOPPEN_MAJOR.get(img.get("koppen_major", ""), img.get("koppen_major", "")),
            "descriptor": img.get("descriptor", ""),
        },
        "geo_oracle": oracle.oracle_block(true_lab, state, geo_flag),
        "dialogue": dialogue,
        "cot": cot,
        "gold": gold,
        "counterfactual": counterfactual,
        "split": split,
        "reasoning_capable": bool(geo_informative and len(plausible) >= 1),
    }
