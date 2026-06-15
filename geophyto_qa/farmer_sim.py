"""
geophyto_qa.farmer_sim
======================
Dynamic farmer<->expert dialogue simulation (PatientSim-style), replacing the
fixed 6-turn template in render_item.

  * EXPERT  = GROUNDED. Its turns are derived deterministically from the decision
              graph (decisive sign, distractor sign, gold diagnosis, management),
              so the gold answer is never altered.
  * FARMER  = DYNAMIC. A persona-controlled LLM agent (vLLM) that speaks in lay
              language, grounded only on the photo's lay observation, and never
              told the diagnosis (so it cannot leak it). Persona = one of
              geophyto_qa.personas.PERSONAS (the four PatientSim axes).

The conversation length is DYNAMIC: the persona decides how many times the farmer
reacts, so anxious/talkative growers produce longer consultations than reticent
ones (the expert always delivers the diagnosis+rule-out at minimum).

This is a standalone transform:
    geophyto_qa.jsonl  --(persona farmer sim)-->  geophyto_qa_sim.jsonl
The template build is untouched and remains the baseline.

Run on a GPU node:
    sbatch geophyto_qa/slurm/step10_simulate_dialogues.slurm
Offline smoke (no GPU, templated stub farmer):
    python -m geophyto_qa.farmer_sim --backend stub --limit 5 --out /tmp/sim.jsonl
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from geophyto_qa.render_item import _sign, _strip, _lc          # noqa: E402
from geophyto_qa.schema import decisive_fork                    # noqa: E402
from geophyto_qa.build import graphs_by_pair                    # noqa: E402
from geophyto_qa import personas                                # noqa: E402

MODEL = os.environ.get("FARMER_MODEL", "Qwen/Qwen2.5-7B-Instruct")


# --------------------------------------------------------------------------- #
# Grounding: everything the farmer (lay) and the grounded expert need, pulled
# from a built template item + its decision graph.
def grounding_for(item, graphs):
    pid = item["lookalike"]["pair_id"]
    rec = graphs.get(pid)
    if not rec:
        return None
    g = rec["graph"]
    lay = g.get("lay") or {}
    true_member = item["item_id"].rsplit("-", 1)[-1]          # 'a' or 'b'
    dec_true_full = item["gold"]["evidence_from_image"]
    dec_dist_full = lay.get("decisive_lay_a") if true_member == "b" else lay.get("decisive_lay_b")
    fk = decisive_fork(g) or {}
    # lay observation: stored in the PERCEIVE CoT step as "On the host part: <obs>."
    perceive = next((c["text"] for c in item.get("cot", []) if c["step"] == "PERCEIVE"), "")
    lay_obs = perceive.split(":", 1)[1].strip().rstrip(".") if ":" in perceive else \
        (lay.get("farmer_lay_report") or "something looks wrong")
    return {
        "item_id": item["item_id"],
        "host": item["grounding"]["host"],
        "part": item["grounding"].get("anatomical_part", ""),
        "lay_observation": lay_obs,
        "true": item["gold"]["diagnosis"],
        "distractor": item["gold"]["ruled_out"],
        "dec_true": _sign(dec_true_full),
        "dec_dist": _sign(dec_dist_full or ""),
        "management": item["gold"].get("management", ""),
        # technical decisive signs (BOTH members) — used only for anti-leakage
        "tech": [t for t in (fk.get("a_signal"), fk.get("b_signal")) if t],
    }


# --------------------------------------------------------------------------- #
# GROUNDED expert turns (content fixed by the decision graph).
def expert_turns(gr):
    diag = (f"Looking at your photo, I can see {_lc(_strip(gr['dec_true']))}. "
            f"That points to {gr['true']} rather than {gr['distractor']}, "
            f"which would instead show {_lc(_strip(gr['dec_dist']))}.")
    m = _strip(gr["management"])
    manage = (m[:1].upper() + m[1:] + ".") if m else \
        "Manage it promptly with the labeled control for this disease."
    reaffirm = (f"What I can see in your photo — {_lc(_strip(gr['dec_true']))} — "
                f"is what makes this {gr['true']} and not {gr['distractor']}, so it's worth acting on.")
    return {"diagnose": diag, "manage": manage, "reaffirm": reaffirm}


# Persona -> which optional stages/turns happen, so dialogue length varies.
def round_plan(persona):
    p = persona["personality"]
    stages = ["diagnose", "manage"]
    if p not in ("reticent", "impatient"):       # they cut it short after management
        stages.append("reaffirm")
    closing = p in ("talkative", "overanxious", "distrustful")
    return stages, closing


FARMER_DIRECTIVE = {
    "open":   "Start the conversation: describe what looks wrong and ask what it is.",
    "react":  "The expert just told you what it is and what to look for. React in character "
              "and ask what you should do about it. Do NOT name any disease.",
    "follow": "Respond in character to the expert's advice — express a worry, a doubt, or a "
              "clarifying question. Do NOT name any disease.",
    "close":  "Wrap up the conversation in one short line, in character.",
}

# Guaranteed-clean fallbacks if the LLM leaks a label/sign.
def _fallback(kind, gr):
    return {
        "open":   f"My {gr['host']} {gr['part'] or 'plant'} — {_lc(gr['lay_observation'])}. What is this?",
        "react":  "Is it serious? What should I do about it?",
        "follow": "My neighbor says it's just the weather — are you sure?",
        "close":  "Alright, thank you.",
    }[kind]


def _leaks(text, gr):
    t = (text or "").lower()
    if not t.strip():
        return True
    bad = [gr["true"].lower(), gr["distractor"].lower()] + [s.lower() for s in gr["tech"]]
    return any(b and b in t for b in bad)


def _transcript(turns):
    out = []
    for tn in turns:
        who = "You (farmer)" if tn["speaker"] == "farmer" else "Expert"
        out.append(f"{who}: {tn['text']}")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
def simulate(gr, persona, farmer_fn):
    """Run one dynamic consultation. farmer_fn(system, transcript, directive)->str."""
    sysp = personas.system_prompt(persona, gr["host"], gr["part"], gr["lay_observation"])
    et = expert_turns(gr)
    stages, closing = round_plan(persona)

    turns, repairs = [], 0

    def farmer(kind, has_image=False):
        nonlocal repairs
        txt = farmer_fn(sysp, _transcript(turns), FARMER_DIRECTIVE[kind])
        txt = _strip(txt) + ("." if txt and not txt.rstrip().endswith((".", "?", "!")) else "")
        if _leaks(txt, gr):
            txt = _fallback(kind, gr)
            repairs += 1
        turns.append({"turn": f"F{sum(1 for x in turns if x['speaker']=='farmer')+1}",
                      "speaker": "farmer", "text": txt, "has_image": has_image})

    def expert(stage):
        turns.append({"turn": f"E{sum(1 for x in turns if x['speaker']=='expert')+1}",
                      "speaker": "expert", "text": et[stage], "has_image": False})

    farmer("open", has_image=True)               # F1 carries the image
    for i, stage in enumerate(stages):
        expert(stage)
        if i == 0:
            farmer("react")
        elif stage != "reaffirm":
            farmer("follow")
    if closing:
        farmer("close")

    return turns, {"persona": persona["id"], "n_turns": len(turns),
                   "leak_repairs": repairs, "mode": "sim"}


# --------------------------------------------------------------------------- #
def make_stub_farmer():
    """Deterministic, persona-free templated farmer for offline testing (no GPU).
    Produces clean lay lines so the loop / dynamic length / checks can be verified."""
    LINES = {
        "open":   "There's something wrong with my plants and I'm not sure what it is. Can you tell?",
        "react":  "Oh no — is it going to spread? What do I do now?",
        "follow": "Are you really sure? A neighbor said it was just the weather.",
        "close":  "Okay, thank you for the help.",
    }

    def fn(system, transcript, directive):
        for k, v in LINES.items():
            if FARMER_DIRECTIVE[k] == directive:
                return v
        return "Okay."
    return fn


def make_vllm_farmer(model=MODEL, temperature=0.8, max_tokens=80):
    """Persona-driven farmer backed by a local instruct model via vLLM."""
    from transformers import AutoProcessor
    from vllm import LLM, SamplingParams
    proc = AutoProcessor.from_pretrained(model)
    llm = LLM(model=model, max_model_len=4096, gpu_memory_utilization=0.90,
              dtype="bfloat16", enforce_eager=True)
    sp = SamplingParams(temperature=temperature, top_p=0.9, max_tokens=max_tokens)

    def fn(system, transcript, directive):
        user = ((transcript + "\n\n") if transcript else "") + directive + \
            "\nYour next message as the farmer:"
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        text = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        out = llm.generate([text], sp)[0].outputs[0].text
        return out.strip().strip('"').split("\n")[0]
    return fn


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=os.path.join(ROOT, "geophyto_qa.jsonl"))
    ap.add_argument("--out", default=os.path.join(ROOT, "geophyto_qa_sim.jsonl"))
    ap.add_argument("--backend", choices=["vllm", "stub"], default="vllm")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--temperature", type=float, default=0.8)
    ap.add_argument("--max-tokens", type=int, default=80)
    ap.add_argument("--seed", type=int, default=20260613)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    items = [json.loads(l) for l in open(args.inp)]
    if args.limit:
        items = items[:args.limit]
    graphs = graphs_by_pair()
    farmer_fn = make_stub_farmer() if args.backend == "stub" else \
        make_vllm_farmer(args.model, args.temperature, args.max_tokens)

    print(f"[farmer_sim] {len(items)} items | backend={args.backend} | "
          f"{len(personas.PERSONAS)} personas", flush=True)

    n_ok, n_skip, total_repairs = 0, 0, 0
    pcount = collections.Counter()
    turnhist = collections.Counter()
    with open(args.out, "w") as fh:
        for i, it in enumerate(items):
            gr = grounding_for(it, graphs)
            if gr is None:
                n_skip += 1
                continue
            persona = personas.assign(it["item_id"], args.seed)
            turns, meta = simulate(gr, persona, farmer_fn)
            it["dialogue"] = turns
            it["dialogue_meta"] = {**meta, "persona_axes": {k: persona[k] for k in
                                   ("personality", "language_proficiency", "recall", "confusion")}}
            fh.write(json.dumps(it) + "\n")
            n_ok += 1
            total_repairs += meta["leak_repairs"]
            pcount[persona["personality"]] += 1
            turnhist[meta["n_turns"]] += 1
            if (i + 1) % 100 == 0:
                print(f"  {i+1}/{len(items)} ...", flush=True)

    print(f"[farmer_sim] wrote {n_ok} items -> {args.out}  (skipped {n_skip} w/o graph)")
    print(f"  anti-leakage repairs: {total_repairs}")
    print(f"  turn-count distribution: {dict(sorted(turnhist.items()))}")
    print(f"  personality distribution: {dict(pcount)}")


if __name__ == "__main__":
    main()
