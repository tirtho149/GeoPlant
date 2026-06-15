# GeoPlant / `geophyto_qa` — pipeline & per-step contracts

Image-grounded **look-alike plant-disease diagnosis** VQA. Each item = one real
Bugwood photo of a disease + a farmer↔expert dialogue where the expert reads the
**decisive visible sign** and tells the disease apart from its documented look-alike.
Pure image → label. (Package name is legacy; the earlier geography idea was dropped.)

See [`README.md`](README.md) for the quickstart. This file is the step-by-step
contract (inputs → command → outputs). Each step is one `.slurm` in
`geophyto_qa/slurm/`; logs land in `geophyto_qa/logs/<step>_%j.{out,err}`.

---

## The item (one output record)

```json
{
  "item_id": "gpqa-<imgnum>-<a|b>",
  "image": {"url": "...bugwoodcloud.org/...", "image_number": "...", "attribution": "...", "license_note": "per-image CC; see Bugwood"},
  "lookalike": {"pair_id": "...", "crop": "...", "true": "<diagnosis>", "distractor": "<look-alike>",
                "evidence": {"web_verified": true, "web_quote": "...", "web_source_url": "...", "clip": {...}}},
  "grounding": {"host": "...", "disease": "<true>", "anatomical_part": "...", "descriptor": "...", "state": "<provenance only>"},
  "split": "train | test_random | test_heldout_species | test_heldout_region",
  "dialogue": [ /* dynamic length (persona-driven); F1 carries the image */ ],
  "dialogue_meta": {"mode": "sim", "persona": "...", "n_turns": 0, "leak_repairs": 0, "persona_axes": {}},
  "cot": [ {"step": "PERCEIVE|READ_SIGN|RULE_OUT|CONCLUDE", "cites": "...", "text": "..."} ],
  "gold": {"diagnosis": "...", "ruled_out": "...", "evidence_from_image": "<the visible decisive sign>",
           "management": "...", "answerable_from_image": true}
}
```

`state` is kept only as image provenance; it is **not** used in the dialogue, CoT, or gold.

## Pipeline

```
BugWood_Diseases_enriched.csv
   │
 1 mine_pairs ............ within-crop candidate look-alike pairs  -> pairs/candidates.json
 2 web-confirm (GATE) .... credible source quote+URL that the two are confused -> lookalike/web_evidence.json
 3 flava_confuse (ROUTER). FLAVA bidirectional-entailment confusability -> lookalike/flava_scores.json
 4 verify_pairs .......... confirmed = web; FLAVA score attached   -> lookalike/confirmed_lookalikes.json
 5 graphgen .............. one discriminator decision graph / pair (decisive visible sign) -> graphs/generated/
 6 vlm_label ............. per-image: is the deciding sign visible?-> lookalike/vlm_labels.json
 7 build (farmer_sim) ... DYNAMIC dialogue: persona farmer (vLLM) + grounded expert
                          + CoT/gold/self-check -> geophyto_qa.jsonl   [GPU]
 8 check_splits .......... assert no image spans two splits
```

### Step 7 — BUILD = dynamic dialogue, PatientSim-style

The dataset builder is `geophyto_qa.farmer_sim` (it replaces the old fixed 6-turn
template; `geophyto_qa.build` is kept only as a CPU baseline/ablation). It is a
DYNAMIC two-agent consultation adapted from
[PatientSim](https://github.com/dek924/PatientSim):

- **Farmer = LLM agent** (local model via vLLM), controlled by a persona along the
  four PatientSim axes (`geophyto_qa.personas`): personality · language
  proficiency (CEFR) · history recall · confusion — a curated ~37-combo set, one
  assigned per item by a stable hash so it is reproducible. The farmer is grounded
  ONLY on the lay observation and is never told the diagnosis, so it cannot leak it.
- **Expert = grounded** — its turns are derived from the decision graph (decisive
  sign, distractor sign, gold diagnosis, management), so the gold answer is
  unchanged. Conversation length is dynamic (anxious/talkative growers talk longer).
- Item selection / CoT / gold / self-check are SHARED with the baseline
  (`build.select_items` + `render_item.item_skeleton` + `build.selfcheck`), so the
  only difference from the template is the dialogue. Anti-leakage is enforced per
  farmer turn (label / technical sign never appears; offending turns fall back to a
  clean line).

| step | module | node | role |
|------|--------|------|------|
| 1 | `mine_pairs` | CPU | within-crop confusable candidate pairs (ranked) |
| 2 | `lookalike.gen_sweep_workflow` → Workflow → `lookalike.persist_sweep` | LLM/web | **the gate**: a pair counts only if a credible source says the two are confused |
| 3 | `lookalike.flava_confuse` | GPU | FLAVA (natively-multimodal) **bidirectional-entailment** confusability, organ-matched; attached as evidence. CLIP (`clip_confuse`) kept as a baseline/ablation |
| 4 | `lookalike.verify_pairs` | CPU | `confirmed = web`; FLAVA bidir score attached |
| 5 | `gen_lay_workflow` → Workflow → `persist_lay` | LLM/web | per-pair decision graph: the decisive sign + lay layer + management |
| 6 | `lookalike.vlm_label` | GPU | per-image: deciding sign visible? close-up? organ? |
| 7 | `farmer_sim` | GPU | BUILD: select items + dynamic persona dialogue (farmer=vLLM, expert=graph-grounded) + CoT/gold + self-check. Baseline = `build` (CPU template) |
| 8 | `audit.check_splits` | CPU | image-level split-leakage gate |

## The decision graph (step 5)

One graph per pair distinguishes member_a vs member_b through ordered forks, exactly
one marked **decisive** (the sign that resolves it on its own), plus a **lay layer**
(`farmer_lay_report`, `decisive_lay_a/b`) and `management_a/b`. `render_item` uses the
lay decisive sign for the dialogue and stores the full form in `gold.evidence_from_image`.
Gold exemplars: `graphs/gold/`; LLM-authored: `graphs/generated/`.

## Self-check (every item must pass; build prints `PASS`)

- **Anti-leakage:** the graph's *technical* decisive sign never appears in a farmer turn.
- CoT ends in **CONCLUDE** and contains a **READ_SIGN** step (sign read from the image).
- `diagnosis ≠ distractor`; `answerable_from_image = true`; F1 carries the image.
- Look-alike evidence present (web source URL).

## Build & verify

```bash
source /work/mech-ai-scratch/tirtho/.venv/bin/activate
# BUILD = dynamic dialogue (GPU; prints PASS + coverage)
python -m geophyto_qa.farmer_sim --backend vllm --min-imgs 12 \
    --seed 20260613 --out geophyto_qa.jsonl
python -m geophyto_qa.audit.check_splits --jsonl geophyto_qa.jsonl

# offline plumbing smoke (no GPU, templated stub farmer):
python -m geophyto_qa.farmer_sim --backend stub --max 20 --out /tmp/smoke.jsonl
# fixed-template BASELINE (CPU, for ablation only):
python -m geophyto_qa.build --min-imgs 12 --seed 20260613 --out geophyto_qa_template.jsonl
```

Coverage (`geophyto_qa.coverage.json`) lists every confirmed pair still **pending a
graph** — nothing is silently dropped. Deterministic via `--seed 20260613`.

## Current status

**1,453 items · 151 confirmed look-alike pairs · 188 graphs used · self-check PASS · no split leakage.**
Splits: train 844 / test_random 163 / test_heldout_species 393 / test_heldout_region 53.
To scale: author graphs for the pending pairs (step 5) and re-build.
