"""
geophyto_qa.render_item
=======================
Image -> look-alike label renderer (geography-free).

Each item is grounded on ONE real Bugwood photo of the TRUE disease. The farmer
shows the photo and a lay observation; the expert reads the DECISIVE VISIBLE SIGN
from the image, diagnoses the true disease, and rules out its look-alike. The task
is purely visual: tell two confusable diseases apart from the picture.

Anti-leakage (enforced in build.selfcheck): the graph's *technical* decisive sign
never appears in any farmer turn — the farmer uses lay language only.
"""
from __future__ import annotations

import random
import re
from typing import Any, Dict, Optional

from geophyto_qa.schema import decisive_fork


def _sign(dec: str) -> str:
    """Turn a lay decisive instruction into a short noun phrase naming the sign.
    Lay signs are written "Look at X: <the actual sign>" — keep the part after the
    colon (the sign itself), dropping the "where to look" instruction."""
    s = re.split(r"[;.]", (dec or "").strip())[0].strip()
    if ":" in s:
        s = s.split(":", 1)[1].strip()
    s = re.sub(r"^flip\s+the\s+lea\w+\s+over[, ]*(and\s+)?", "", s, flags=re.I)
    m = re.match(r"^(look|check|examine|inspect|search)\b.*?\bfor\b\s+(.*)$", s, flags=re.I)
    if m:
        s = m.group(2)
    s = s.strip().strip(",")
    if "," in s and len(s.split(",")[0]) >= 20:
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


def _clean_mgmt(mgmt: str, disease: str) -> str:
    """Drop a leading "<disease>:" the graph sometimes prepends, to avoid double-naming."""
    s = (mgmt or "").strip()
    if ":" in s:
        head, rest = s.split(":", 1)
        if head.strip().lower() == (disease or "").strip().lower():
            return rest.strip()
    return s


def render(rec: Dict[str, Any], graph: Dict[str, Any], img: Dict[str, Any],
           true_member: str, split: str, vlm: Dict[str, Any],
           seed_salt: int) -> Optional[Dict[str, Any]]:
    """Render one image->label item, or None if the image can't form a clean item."""
    if not vlm or not vlm.get("is_closeup"):
        return None                        # drop wide field/landscape shots
    if not vlm.get("decisive_sign_visible"):
        return None                        # image MUST show the deciding sign
    lay = graph.get("lay")
    if not lay:
        return None

    rng = random.Random(f"{img['img']}|{seed_salt}")
    a_lab, b_lab = rec["member_a_label"], rec["member_b_label"]
    true_lab = a_lab if true_member == "a" else b_lab
    dist_lab = b_lab if true_member == "a" else a_lab
    dec_true_full = lay["decisive_lay_a"] if true_member == "a" else lay["decisive_lay_b"]
    dec_dist_full = lay["decisive_lay_a"] if true_member == "b" else lay["decisive_lay_b"]
    dec_true = _sign(dec_true_full)
    dec_dist = _sign(dec_dist_full)
    mgmt = _clean_mgmt(graph["management_a"] if true_member == "a" else graph["management_b"], true_lab)

    host = img.get("host_common") or rec["crop"]
    part = vlm.get("anatomical_part", "")
    farmer_obs = _strip(vlm.get("lay_observation") or lay["farmer_lay_report"])
    # guard: never let the technical sign leak into the farmer's words
    _dfk = decisive_fork(graph) or {}
    if any(s and s.lower() in farmer_obs.lower() for s in (_dfk.get("a_signal"), _dfk.get("b_signal"))):
        farmer_obs = _strip(lay["farmer_lay_report"])

    F1 = f"My {host} {part or 'plant'} — {_lc(farmer_obs)}. What is this?"
    E1 = (f"Looking at your photo, I can see {_lc(_strip(dec_true))}. "
          f"That points to {true_lab} rather than {dist_lab}, "
          f"which would instead show {_lc(_strip(dec_dist))}.")
    F2 = "Will it spread, and what should I do about it?"
    _m = _strip(mgmt)
    E2 = (_m[:1].upper() + _m[1:] + ".") if _m else "Manage it promptly with the labeled control for this disease."
    F3 = rng.choice(_PUSHBACK)
    E3 = (f"Weather can play a part, but what I can see in your photo — {_lc(_strip(dec_true))} — "
          f"is what makes this {true_lab} and not {dist_lab}, so it's worth acting on.")

    cot = [
        {"step": "PERCEIVE", "cites": "image (VLM lay observation)",
         "text": f"On the {host} {part}: {_lc(farmer_obs)}."},
        {"step": "READ_SIGN", "cites": "image (decisive sign visible)",
         "text": f"The photo shows {_lc(_strip(dec_true))} — the deciding sign."},
        {"step": "RULE_OUT", "cites": "decision graph",
         "text": f"{dist_lab} would instead show {_lc(_strip(dec_dist))}, which is not present."},
        {"step": "CONCLUDE", "cites": "image",
         "text": f"From the visible sign this is {true_lab}, not {dist_lab}."},
    ]

    return {
        "item_id": f"gpqa-{img['img']}-{true_member}",
        "kind": rec.get("kind", "disease"),
        "image": {"url": img["url"], "image_number": img["img"],
                  "attribution": img.get("cite", ""), "license_note": "per-image CC; see Bugwood"},
        "lookalike": {"pair_id": rec["pair_id"], "crop": rec["crop"],
                      "true": true_lab, "distractor": dist_lab},
        "grounding": {"host": host, "disease": true_lab,
                      "anatomical_part": part, "descriptor": img.get("descriptor", ""),
                      "state": img.get("state", "")},   # provenance metadata only (not used)
        "split": split,
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
                 "answerable_from_image": True},
    }
