"""
geophyto_qa.render_two_lane
==========================
Two-lane, anti-leakage renderer (the redesign).

Lane is decided PER IMAGE from the VLM label:

  LANE A — image-decisive (real VQA, geography OUT):
     the decisive sign is VISIBLE in this photo (vlm.decisive_sign_visible).
     The farmer reports only the image-grounded lay observation; the expert
     reads the decisive sign FROM the photo and rules the distractor out.
     Changing location must NOT change the answer (control).

  LANE B — image-ambiguous (geography decisive, the novelty):
     the decisive sign is NOT visible, so the photo underdetermines the call.
     Emitted ONLY when the contributor-de-biased TRAIN prior in the image's
     region genuinely favors the TRUE member over the distractor — then the
     gold = that prior-favored member, and geography is load-bearing. Changing
     location to a region favoring the distractor should flip the answer.

Anti-leakage gate (enforced in build.selfcheck): the graph's *technical* decisive
signal never appears in any farmer turn. The farmer uses lay language only; the
lay form of the sign may appear in Lane A (per the design — the sign IS visible),
but the pathognomonic technical wording never does.
"""
from __future__ import annotations

import random
import re
from typing import Any, Dict, Optional

from geophyto_qa.regions import region_of
from geophyto_qa.schema import decisive_fork


def _sign(dec: str) -> str:
    """Turn a lay decisive instruction ("Flip the leaf and look for a fuzzy mat;
    ...") into a short noun phrase naming the sign ("a fuzzy mat")."""
    s = re.split(r"[;.]", (dec or "").strip())[0].strip()
    s = re.sub(r"^flip\s+the\s+lea\w+\s+over[, ]*(and\s+)?", "", s, flags=re.I)
    m = re.match(r"^(look|check|examine|inspect|search)\b.*?\bfor\b\s+(.*)$", s, flags=re.I)
    if m:
        s = m.group(2)
    s = s.strip().strip(",")
    if "," in s and len(s.split(",")[0]) >= 20:    # keep the core noun phrase
        s = s.split(",")[0]
    return (s[:1].lower() + s[1:]) if s else s

_PUSHBACK = [
    "My neighbor says it's just the weather and nothing to worry about.",
    "Someone told me this always clears up on its own.",
    "A friend thinks it's just fertilizer burn.",
]


def _strip(s: str) -> str:
    return (s or "").rstrip(". ").strip()


def _lc(s: str) -> str:
    return s[:1].lower() + s[1:] if s else s


def _region_prior(oracle, disease, region):
    return oracle.region_w.get(disease, {}).get(region, 0)


def render(rec: Dict[str, Any], graph: Dict[str, Any], img: Dict[str, Any],
           true_member: str, oracle, split: str, vlm: Dict[str, Any],
           seed_salt: int, lane_b_margin: int = 2) -> Optional[Dict[str, Any]]:
    """Render one item, or None if the image/pair can't form a clean item."""
    if not vlm or not vlm.get("is_closeup"):
        return None                       # drop wide field/landscape shots
    lay = graph.get("lay")
    if not lay:
        return None                       # graph lacks the lay layer

    rng = random.Random(f"{img['img']}|{seed_salt}")
    a_lab, b_lab = rec["member_a_label"], rec["member_b_label"]
    true_lab = a_lab if true_member == "a" else b_lab
    dist_lab = b_lab if true_member == "a" else a_lab
    dec_true_full = lay["decisive_lay_a"] if true_member == "a" else lay["decisive_lay_b"]
    dec_dist_full = lay["decisive_lay_a"] if true_member == "b" else lay["decisive_lay_b"]
    dec_true = _sign(dec_true_full)        # short noun phrase for the dialogue
    dec_dist = _sign(dec_dist_full)
    mgmt = graph["management_a"] if true_member == "a" else graph["management_b"]

    state = img["state"]; region = region_of(state)
    host = img.get("host_common") or rec["crop"]
    part = vlm.get("anatomical_part", "")
    farmer_obs = _strip(vlm.get("lay_observation") or lay["farmer_lay_report"])
    # Guard: a bad VLM lay_observation can echo the TECHNICAL decisive sign it was
    # shown in the prompt (jargon, or a "I can't see the sign '<sign>'" meta-comment),
    # which would leak the pathognomonic wording into the farmer turn. Fall back to
    # the graph's lay farmer report whenever either member's technical sign appears.
    _dfk = decisive_fork(graph) or {}
    _fo = farmer_obs.lower()
    if any(s and s.lower() in _fo for s in (_dfk.get("a_signal"), _dfk.get("b_signal"))):
        farmer_obs = _strip(lay["farmer_lay_report"])
    sign_visible = bool(vlm.get("decisive_sign_visible"))

    base = {
        "item_id": f"gpqa-{img['img']}-{true_member}",
        "kind": rec.get("kind", "disease"),
        "image": {"url": img["url"], "image_number": img["img"],
                  "attribution": img.get("cite", ""), "license_note": "per-image CC; see Bugwood"},
        "lookalike": {"pair_id": rec["pair_id"], "crop": rec["crop"],
                      "true": true_lab, "distractor": dist_lab},
        "grounding": {"host": host, "disease": true_lab, "state": state, "region": region,
                      "anatomical_part": part, "descriptor": img.get("descriptor", "")},
        "split": split,
    }

    # ---------------- LANE A : image-decisive ---------------- #
    if sign_visible:
        F1 = f"My {host} {part or 'plant'} — {_lc(farmer_obs)}. What is this?"
        E1 = (f"Looking at your photo, I can see {_lc(_strip(dec_true))}. "
              f"That points to {true_lab} rather than {dist_lab}, "
              f"which would instead show {_lc(_strip(dec_dist))}.")
        F2 = "Will it spread, and what should I do about it?"
        E2 = _strip(mgmt) + "."
        F3 = rng.choice(_PUSHBACK)
        E3 = (f"Weather can play a part, but the {_lc(_strip(dec_true))} I can see in your "
              f"photo is what makes this {true_lab} and not {dist_lab}, so it's worth acting on.")
        cot = [
            {"step": "PERCEIVE", "cites": "image (VLM lay observation)",
             "text": f"On the {host} {part}: {_lc(farmer_obs)}."},
            {"step": "READ_SIGN", "cites": "image (decisive sign visible)",
             "text": f"The photo shows {_lc(_strip(dec_true))} — the deciding sign."},
            {"step": "RULE_OUT", "cites": "decision graph",
             "text": f"{dist_lab} would instead show {_lc(_strip(dec_dist))}, which is not present."},
            {"step": "CONCLUDE", "cites": "image",
             "text": f"From the visible sign this is {true_lab}, not {dist_lab}. Geography is not needed."},
        ]
        base.update({
            "lane": "image_decisive",
            "dialogue": [
                {"turn": "F1", "speaker": "farmer", "text": F1, "has_image": True},
                {"turn": "E1", "speaker": "expert", "text": E1, "has_image": False},
                {"turn": "F2", "speaker": "farmer", "text": F2, "has_image": False},
                {"turn": "E2", "speaker": "expert", "text": E2, "has_image": False},
                {"turn": "F3", "speaker": "farmer", "text": F3, "has_image": False},
                {"turn": "E3", "speaker": "expert", "text": E3, "has_image": False},
            ],
            "cot": cot,
            "gold": {"diagnosis": true_lab, "ruled_out": dist_lab,
                     "evidence_from_image": _strip(dec_true_full),
                     "management": _strip(mgmt),
                     "geography_used": False,
                     "answerable_from_image": True},
            "counterfactual": {"control": True, "swap_location_to": "Iowa" if state != "Iowa" else "Ohio",
                               "expected_shift": "No change — the decisive sign is visible in the photo, "
                                                 "so the diagnosis is from the image and location is irrelevant."},
            "evidence": {"vlm_sign_visible": True, "anatomical_part": part,
                         "image_confusable": True},
        })
        return base

    # ---------------- LANE B : image-ambiguous, geography decides ---------------- #
    wt = _region_prior(oracle, true_lab, region)
    wd = _region_prior(oracle, dist_lab, region)
    if not (region and wt > wd and wt >= lane_b_margin):
        return None                       # geography doesn't honestly favor the truth -> skip
    pressure = oracle.local_pressure(true_lab, state)

    # S14 anti-leakage: in Lane B the decisive sign is NOT visible, so its lay/technical
    # wording must NOT appear in any dialogue or CoT text (a text/VLM model would
    # otherwise read the answer-determining vocabulary straight from the prompt). The
    # specific sign survives ONLY in the hidden gold.confirm_action. Ambiguity must
    # hold in BOTH modalities.
    F1 = (f"My {host} {part or 'plant'} — {_lc(farmer_obs)}. I'm farming in {state}. What is this?")
    E1 = (f"From the photo I can see the general problem, but the one feature that would "
          f"separate {true_lab} from {dist_lab} isn't readable in this image. Given you're "
          f"in the {region}, where {_lc(_strip(pressure))}, it's more likely {true_lab}.")
    F2 = "So what should I do, and how can I be sure?"
    E2 = (f"To be certain you'd need a hands-on check of the plant for the deciding sign. "
          f"In the meantime, manage for {true_lab}: {_lc(_strip(mgmt))}.")
    F3 = rng.choice(_PUSHBACK)
    E3 = (f"Without the deciding sign visible in the photo, location is the best guide: in the "
          f"{region} {_lc(_strip(pressure))}, so {true_lab} is the call until a hands-on check "
          f"says otherwise.")
    cot = [
        {"step": "PERCEIVE", "cites": "image (VLM lay observation)",
         "text": f"On the {host} {part}: {_lc(farmer_obs)}."},
        {"step": "SIGN_ABSENT", "cites": "image (decisive sign NOT visible)",
         "text": "The single sign that would separate the two diseases is not visible in this photo."},
        {"step": "GEO", "cites": "contributor-de-biased TRAIN prior",
         "text": f"In the {region}, {_lc(_strip(pressure))} (prior weight {wt} vs {wd} for {dist_lab})."},
        {"step": "CONCLUDE", "cites": "geographic prior",
         "text": f"Photo underdetermines it, so geography tips it to {true_lab}; confirm with a hands-on check of the plant."},
    ]
    # S13 counterfactual: swap to a region where the DISTRACTOR is genuinely MORE
    # plausible than the true member (not merely a region where the true member is
    # rare). If no region favors the distractor, this pair cannot be honestly flipped
    # by geography -> emit it as a no-flip control instead of a bogus shift.
    swap = oracle.swap_to_distractor_region(true_lab, dist_lab, exclude=region)
    if swap:
        counterfactual = {
            "control": False,
            "swap_location_to": swap[0], "swap_region": swap[1],
            "expected_shift": (f"Answer should flip toward {dist_lab}: the photo lacks the "
                               f"deciding sign, and in the {swap[1]} the prior favors {dist_lab} "
                               f"over {true_lab}."),
        }
    else:
        counterfactual = {
            "control": True,
            "swap_location_to": None, "swap_region": None,
            "expected_shift": (f"No change — no US region favors {dist_lab} over {true_lab} in "
                               f"the prior, so location cannot honestly flip this call (control)."),
        }
    base.update({
        "lane": "image_ambiguous",
        "dialogue": [
            {"turn": "F1", "speaker": "farmer", "text": F1, "has_image": True},
            {"turn": "E1", "speaker": "expert", "text": E1, "has_image": False},
            {"turn": "F2", "speaker": "farmer", "text": F2, "has_image": False},
            {"turn": "E2", "speaker": "expert", "text": E2, "has_image": False},
            {"turn": "F3", "speaker": "farmer", "text": F3, "has_image": False},
            {"turn": "E3", "speaker": "expert", "text": E3, "has_image": False},
        ],
        "cot": cot,
        "gold": {"diagnosis": true_lab, "ruled_out": dist_lab,
                 "decided_by": "geographic prior",
                 "confirm_action": _strip(dec_true_full),
                 "management": _strip(mgmt),
                 "geography_used": True, "answerable_from_image": False,
                 "region_prior": {"true": wt, "distractor": wd, "region": region}},
        "counterfactual": counterfactual,
        "evidence": {"vlm_sign_visible": False, "anatomical_part": part,
                     "image_confusable": True},
    })
    return base
