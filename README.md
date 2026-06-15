# Look-alike plant-disease diagnosis VQA (GeoPlant / `geophyto_qa`)

An image-grounded benchmark for telling **confusable plant diseases apart from a
photo**. Each item is a multi-turn farmer↔ag-expert dialogue anchored on one real
image of a disease; the expert reads the **decisive visible sign** from the
photo, gives the diagnosis, and **rules out the look-alike** it is most confused with.

> Pure image → label: the task is visual diagnosis between two documented look-alikes.
> Source = the **CyAg curated ImageFolder** dataset (`<Host>/<Disease>/<*.jpg>`, ~1.1M
> images / 552 hosts). Set `GPQA_SOURCE` to use another directory. (The package name
> `geophyto_qa` is legacy — earlier versions explored geography; dropped for image+label.)

Each item carries: the local image path, `host`/`organ`,
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
geophyto_qa.jsonl       the built dataset
data_source.py          ImageFolder loader (GPQA_SOURCE; default = CyAg curated)
GEOPHYTO_QA_README.md   pipeline design + per-step I/O contracts
docs/                   design notes, decision-graph source
```

> Heavy third-party inputs (the image dataset, rasters, PlantVillage) are **not** in
> this repo — see [Data & attribution](#data--attribution).

## Step-by-step data curation

Each step = one SLURM file in `geophyto_qa/slurm/` (logs → `geophyto_qa/logs/`).

| # | step | command (module) | output |
|---|------|------------------|--------|
| input | source dataset | ImageFolder `<Host>/<Disease>/<*.jpg>` via `data_source` (`GPQA_SOURCE`, default = CyAg curated) | rows: img id + local path + crop + disease |
| 0 | **label QA** (LLM-as-judge) ⚙ | `geophyto_qa.quality.disease_label_judge` | `quality/disease_label_full_report.json` (gates mining) |
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

## Running it — one SLURM job per step, run in order

Every step is its **own** `sbatch` script in `geophyto_qa/slurm/`. Run them **one at
a time, in order**, waiting for each to finish before launching the next (each step
consumes the previous step's output). All steps read the dataset through
`GPQA_SOURCE` (default = the CyAg ImageFolder); set it once to switch datasets. Logs
land in `geophyto_qa/logs/<step>_%j.{out,err}`.

| order | `sbatch geophyto_qa/slurm/…` | node | does | output |
|---|---|---|---|---|
| 0 | `step00_label_judge.slurm` | CPU + `claude` | LLM-as-judge crop+disease **label QA**; gates mining | `quality/disease_label_full_report.json` |
| 1 | `step01_mine_pairs.slurm` | CPU | mine within-crop candidate pairs (honors step-0 gate) | `pairs/candidates.json` |
| 2 | `step02_identify_pairs.slurm` | CPU | pair manifest + web work-list | `pairs/pair_manifest.*`, `needs_web.json` |
| 3 | `step03_web_confirm_gen.slurm` ⚙ | LLM/web | **GATE**: web-confirm each pair is a documented look-alike | `lookalike/web_evidence.json` |
| 4 | `step04_flava_sweep.slurm` | GPU | **ROUTER**: FLAVA bidirectional-entailment confusability | `lookalike/flava_scores.json` |
| 5 | `step05_verify_pairs.slurm` | CPU | confirmed = web; attach FLAVA score; drop synonyms | `lookalike/confirmed_lookalikes.json` |
| 6 | `step06_graph_gen.slurm` ⚙ | LLM/web | author one discriminator decision graph per pair | `graphs/generated/*.json` |
| 7 | `step07_vlm_label.slurm` | GPU | per-image: deciding sign visible? + lay observation | `lookalike/vlm_labels.json` |
| 8 | `step08_build.slurm` | GPU | **BUILD** = dynamic persona dialogue + CoT/gold + self-check | `geophyto_qa.jsonl` |
| 9 | `step09_check_splits.slurm` | CPU | assert no image spans two splits | PASS/FAIL |

⚙ = run through the Claude Code Workflow engine (generate a Workflow script, run it,
then persist — see `geophyto_qa/slurm/README.md`). `step04_clip_sweep.slurm` is the
CLIP baseline/ablation for step 4.

```bash
# run each separately, in order (wait for each to complete first)
sbatch geophyto_qa/slurm/step00_label_judge.slurm      # CPU + claude  (label QA)
sbatch geophyto_qa/slurm/step01_mine_pairs.slurm       # CPU
sbatch geophyto_qa/slurm/step02_identify_pairs.slurm   # CPU
sbatch geophyto_qa/slurm/step03_web_confirm_gen.slurm  # ⚙ Workflow (web GATE)
sbatch geophyto_qa/slurm/step04_flava_sweep.slurm      # GPU  (CLIP baseline: step04_clip_sweep)
sbatch geophyto_qa/slurm/step05_verify_pairs.slurm     # CPU
sbatch geophyto_qa/slurm/step06_graph_gen.slurm        # ⚙ Workflow (decision graphs)
sbatch geophyto_qa/slurm/step07_vlm_label.slurm        # GPU
sbatch geophyto_qa/slurm/step08_build.slurm            # GPU  -> geophyto_qa.jsonl
sbatch geophyto_qa/slurm/step09_check_splits.slurm     # CPU
```

### 10-sample smoke (one batch, no GPU/LLM, non-destructive)
```bash
sbatch geophyto_qa/slurm/run_smoke10.slurm     # template build of 10 items + split check
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

- Images come from the **CyAg curated ImageFolder** dataset (local; `GPQA_SOURCE`).
  Each item records the local image path + the source-dataset prefix from the file
  name (e.g. `Bugwood_`, `CDDM_`) as provenance. The dataset is **not** redistributed
  in this repo; it is subject to its constituent sources' own licenses.
- Look-alike confirmation cites a credible extension/university/peer-reviewed source.
- *No code license set yet (defaults to all-rights-reserved).*
