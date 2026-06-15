"""
geophyto_qa.personas
====================
Farmer personas for the dynamic farmer<->expert simulation (geophyto_qa.farmer_sim),
adapted from PatientSim (dek924/PatientSim) which controls a patient agent along
four axes. Here the *farmer* is the analogue of PatientSim's patient: an LLM agent
that speaks in lay language, grounded ONLY on what is visible in the photo, and
never knows the diagnosis.

Four axes (PatientSim -> farmer):
  personality            how they communicate (plain, anxious, distrustful, ...)
  language_proficiency   CEFR-style fluency (C1 / B1 / A2)
  recall                 crop-management history recall (high / medium / low)
  confusion              cognitive confusion / consistency (none / mild / high)

A curated ~37-combination set (PatientSim-style: not the full 6x3x3x3 product)
is built deterministically. Each item is assigned ONE persona by a stable hash of
its item_id + seed, so the dataset is reproducible.
"""
from __future__ import annotations

import hashlib

# --------------------------------------------------------------------------- #
# Axis values -> a short second-person behavioral instruction for the farmer.
PERSONALITY = {
    "plain":        "You are cooperative and straightforward; you answer plainly and stay on topic.",
    "overanxious":  "You are very worried about losing the crop and your income; you catastrophize and keep asking whether it will spread or kill the plants.",
    "distrustful":  "You are skeptical of the expert; you push back, mention what a neighbor or an old remedy says, and need convincing.",
    "talkative":    "You ramble and over-share unrelated farm details before getting to the point.",
    "reticent":     "You are terse; you give short, minimal answers and rarely elaborate unless pressed.",
    "impatient":    "You want a quick, cheap fix; you focus on cost and time and get restless with long explanations.",
}

LANGUAGE = {  # CEFR-style proficiency
    "C1": "Speak fluent, articulate English in full sentences.",
    "B1": "Speak intermediate English: simple short sentences, with occasional small grammar slips.",
    "A2": "Speak basic, broken English: very limited vocabulary, short fragmentary phrases.",
}

RECALL = {
    "high":   "You remember your crop's history well: when the symptoms started, prior sprays, recent weather.",
    "medium": "You have a vague memory of the history: approximate dates and treatments.",
    "low":    "You cannot recall the history: you are unsure when it started or what was applied.",
}

CONFUSION = {
    "none": "You are clear-headed and consistent.",
    "mild": "You occasionally muddle small details but you self-correct.",
    "high": "You are easily confused: you mix up details and may contradict something you said earlier.",
}


# --------------------------------------------------------------------------- #
def _curated():
    """A deterministic, PatientSim-style curated set of personas (~37), not the
    full cross product: a neutral baseline per personality, then single-axis
    stressors layered across personalities."""
    out = []

    def add(p, lang, rec, conf):
        out.append({"personality": p, "language_proficiency": lang,
                    "recall": rec, "confusion": conf})

    pers = list(PERSONALITY)
    for p in pers:                                   # 6 neutral baselines
        add(p, "C1", "high", "none")
    for p in pers:                                   # 12 language stressors
        add(p, "B1", "high", "none")
        add(p, "A2", "high", "none")
    for p in pers:                                   # 12 recall stressors
        add(p, "C1", "medium", "none")
        add(p, "C1", "low", "none")
    for p in pers:                                   # 12 confusion stressors
        add(p, "C1", "high", "mild")
        add(p, "C1", "high", "high")

    # de-dup, stamp a stable id, keep a deterministic 37
    seen, uniq = set(), []
    for d in out:
        pid = persona_id(d)
        if pid not in seen:
            seen.add(pid)
            uniq.append({"id": pid, **d})
    uniq.sort(key=lambda d: d["id"])
    return uniq[:37]


def persona_id(d) -> str:
    return f"{d['personality']}.{d['language_proficiency']}.{d['recall']}.{d['confusion']}"


PERSONAS = _curated()


def assign(item_id: str, seed: int = 20260613):
    """Deterministically map an item to one persona (stable across runs)."""
    h = hashlib.sha1(f"{seed}|{item_id}".encode()).hexdigest()
    return PERSONAS[int(h, 16) % len(PERSONAS)]


def system_prompt(persona, host: str, part: str, lay_observation: str) -> str:
    """The farmer agent's system prompt: persona + lay grounding + hard rules.
    The diagnosis and the technical decisive sign are deliberately ABSENT here —
    the farmer cannot leak what it is never told."""
    behav = " ".join([
        PERSONALITY[persona["personality"]],
        LANGUAGE[persona["language_proficiency"]],
        RECALL[persona["recall"]],
        CONFUSION[persona["confusion"]],
    ])
    return (
        "You are a farmer talking to a plant-disease expert about a problem on your crop. "
        "You are NOT an expert and you do NOT know what the disease is.\n\n"
        f"Your crop: {host}. Affected part: {part or 'plant'}.\n"
        f"What you can see (in your own words): {lay_observation}\n\n"
        f"Stay completely in character:\n{behav}\n\n"
        "HARD RULES:\n"
        "- NEVER name any plant disease or pathogen. Refer to the problem only as "
        "'this', 'it', 'the spots', 'the marks', etc.\n"
        "- Use ONLY plain, everyday language. Never use scientific or technical terms.\n"
        "- Describe only what you can visually observe; do not invent a diagnosis.\n"
        "- Keep each message to 1-2 sentences. Output only your spoken words, no labels."
    )
