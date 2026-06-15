# Look-alike plant-disease diagnosis VQA (GeoPlant / `geophyto_qa`)

An image-grounded benchmark for telling **confusable plant diseases apart from a
photo**. Each item is a multi-turn farmer↔ag-expert dialogue anchored on one real
Bugwood image of a disease; the expert reads the **decisive visible sign** from the
photo, gives the diagnosis, and **rules out the look-alike** it is most confused with.

> Pure image → label: the task is visual diagnosis between two documented look-alikes.
> Bugwood-only, USA-only. (The package name `geophyto_qa` is legacy — earlier versions
> explored geography; that idea was dropped in favor of image+label only.)

Each item carries: the Bugwood image (URL + CC attribution), `host`/`organ`,
the **look-alike pair** (`true` vs `distractor`), a dynamic persona-driven dialogue, a grounded
chain-of-thought (PERCEIVE → READ_SIGN → RULE_OUT → CONCLUDE), and the gold
(`diagnosis`, `ruled_out`, `evidence_from_image`, `management`).

---

## Current state (build of 2026-06-14)

- **`geophyto_qa.jsonl` — 1,453 items**, self-check **PASS**, no image leakage across splits.
- **151 confirmed look-alike pairs** (two-level confirmed: web source + CLIP), 188 graphs used.
- Splits: train 844 · test_random 163 · test_heldout_species 393 · test_heldout_region 53.
- Every item is **answerable from the image** (the deciding sign is visible per the VLM label).

## Repository layout

```
geophyto_qa/            the package — one module per curation step
  mine_pairs.py         (1) candidate within-crop look-alike pairs
  lookalike/            (2-4) web-confirm gate + CLIP confusability + per-image VLM labels
  graphgen.py schema.py (5) discriminator decision-graph authoring + validation
  render_item.py              image -> look-alike diagnosis renderer
  build.py              (6) assemble dataset + self-check
  audit/check_splits.py       split-hygiene gate (no image spans two splits)
  slurm/                one .slurm per step + run_smoke10.slurm   <-- run here
  graphs/               decision graphs (gold exemplars + generated)
geophyto_qa.jsonl       the built dataset (1,453 items)
BugWood_Diseases_enriched.csv   source table (host, disease, sci-name, image URL)
GEOPHYTO_QA_README.md   pipeline design + per-step I/O contracts
docs/                   design notes, decision-graph source
```

> Heavy third-party inputs (rasters, PlantVillage, raw Bugwood tables) are **not** in
> this repo — see [Data & attribution](#data--attribution).

## Step-by-step data curation

Each step = one SLURM file in `geophyto_qa/slurm/` (logs → `geophyto_qa/logs/`).

| # | step | command (module) | output |
|---|------|------------------|--------|
| 0 | source table | *(provided)* `BugWood_Diseases_enriched.csv` | host/disease/sci-name/URL rows |
| 1 | mine pairs | `geophyto_qa.mine_pairs` | `pairs/candidates.json` |
| 2 | web-confirm look-alikes ⚙ | `geophyto_qa.lookalike.gen_sweep_workflow` → Workflow → `persist_sweep` | `lookalike/web_evidence.json` |
| 3 | FLAVA bidir-entailment confusability (GPU) | `geophyto_qa.lookalike.flava_confuse` | `lookalike/flava_scores.json` |
| 4 | confirm pairs | `geophyto_qa.lookalike.verify_pairs` | `lookalike/confirmed_lookalikes.json` |
| 5 | author graphs ⚙ | `geophyto_qa.gen_lay_workflow` → Workflow → `persist_lay` | `graphs/generated/*.json` |
| 6 | VLM sign-visibility labels (GPU) | `geophyto_qa.lookalike.vlm_label` | `lookalike/vlm_labels.json` |
| 7 | **build = dynamic dialogue** (GPU) | `geophyto_qa.farmer_sim` (baseline: `geophyto_qa.build`) | **`geophyto_qa.jsonl`** |
| 8 | split-hygiene check | `geophyto_qa.audit.check_splits` | pass/fail gate |

⚙ = LLM/web step run through the Claude Code Workflow engine; all others are plain batch.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install numpy requests                 # CPU steps (mine/confirm/check + template baseline)
pip install torch transformers pillow      # step 3  FLAVA (GPU); add open_clip_torch for the CLIP baseline
pip install vllm transformers pillow       # step 6 VLM labels + step 7 farmer_sim build (GPU)
```

## Quickstart — use the dataset

```bash
python - <<'PY'
import json
rows = [json.loads(l) for l in open("geophyto_qa.jsonl")]
print(len(rows), "items")
it = rows[0]
for t in it["dialogue"]: print(f'  [{t["turn"]}] {t["speaker"]}: {t["text"]}')
print("gold:", it["gold"]["diagnosis"], "| ruled_out:", it["gold"]["ruled_out"])
print("sign:", it["gold"]["evidence_from_image"])
PY
```

## Running it

### 10-sample smoke (one batch, ~1 min, no GPU/LLM, non-destructive)
```bash
sbatch geophyto_qa/slurm/run_smoke10.slurm     # -> geophyto_qa_smoke10.jsonl + split check
```

### Full sweep
```bash
sbatch geophyto_qa/slurm/step01_mine_pairs.slurm
sbatch geophyto_qa/slurm/step02_identify_pairs.slurm
# step03 web-confirm + step05 graph-gen: generate a Workflow script you run in the
# Claude Code Workflow engine, then persist (see geophyto_qa/slurm/README.md).
sbatch geophyto_qa/slurm/step04_flava_sweep.slurm       # GPU (FLAVA bidir-entailment; step04_clip_sweep = CLIP baseline)
sbatch geophyto_qa/slurm/step05_verify_pairs.slurm
sbatch geophyto_qa/slurm/step07_vlm_label.slurm         # GPU
sbatch geophyto_qa/slurm/step08_build.slurm             # GPU: dynamic dialogue -> geophyto_qa.jsonl
sbatch geophyto_qa/slurm/step09_check_splits.slurm
```

### Build = dynamic (PatientSim-style) dialogue

Step 7/`step08_build` IS the dynamic builder: each item's farmer↔expert
consultation is generated live — farmer = vLLM agent with one of ~37 personas
along PatientSim's four axes; expert stays graph-grounded so gold is unchanged;
turn count varies by persona. Item selection / CoT / gold / self-check are shared
with the baseline, so only the dialogue differs.

```bash
sbatch geophyto_qa/slurm/step08_build.slurm     # GPU -> geophyto_qa.jsonl (PASS + coverage)
# offline plumbing smoke (no GPU, templated stub farmer):
python -m geophyto_qa.farmer_sim --backend stub --max 20 --out /tmp/smoke.jsonl
# fixed-template BASELINE (CPU, ablation only):
python -m geophyto_qa.build --min-imgs 12 --seed 20260613 --out geophyto_qa_template.jsonl
```

### Manual review PDF (paired look-alikes, one pair per page)
```bash
python scripts/make_review_pdf.py --out geophyto_qa_review10.pdf --n 10
```

## Determinism

All builds use `--seed 20260613` and self-check every item (must print `PASS`):
anti-leakage (technical sign never in a farmer turn), CoT ends in CONCLUDE with a
READ_SIGN step, diagnosis ≠ distractor, answerable-from-image, F1 carries the image.

## Data & attribution

- Images are hosted by **Bugwood.org** under **per-image CC licenses**; the dataset
  references image URLs + attribution, it does not redistribute the images.
- Look-alike confirmation cites a credible extension/university/peer-reviewed source.
- Heavy inputs (raw Bugwood tables, PlantVillage, rasters) are excluded; subject to
  their own licenses. *No code license set yet (defaults to all-rights-reserved).*
