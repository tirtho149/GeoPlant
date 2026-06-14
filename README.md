# GeoPhyto-QA — geography-aware look-alike plant-disease diagnosis VQA

Image-grounded, multi-turn **farmer ↔ ag-expert** dialogues in which the expert
reasons through a **look-alike decision graph** to tell apart two confusable plant
diseases — and the reasoning is **geography-aware** (region / season / local disease
pressure decide the call). Diagnosis, not geolocation. Bugwood-only, USA-only.

Every confirmed look-alike pair is routed into one of two lanes:

| Lane | what decides | geography | counterfactual |
|------|--------------|-----------|----------------|
| **A — image-decisive** | the visible sign in the photo | no-flip **control** | answer stays put when region is swapped |
| **B — image-ambiguous** | **geography breaks the tie** (sign not separable in-pixel) | **load-bearing** | answer should flip when region flips |

Lane B is the novelty — and its gold rides on a regional prior, so the repo includes
a **citation-based prior-validation audit** (Phase D) to test that prior before trusting it.

---

## Repository layout

```
geophyto_qa/            the package — one module per curation step
  mine_pairs.py         (1) candidate look-alike pairs
  lookalike/            (2-4) web-confirm gate + CLIP router + per-image VLM labels
  graphgen.py schema.py (5) decision-graph authoring + validation
  geo_oracle.py               contributor-de-biased regional prior
  render_two_lane.py          two-lane dialogue/CoT renderer
  build.py              (6) assemble dataset + self-check
  audit/                (7) prior validation: resolve / research / score / apply
  slurm/                one .slurm per step + submit_audit_chain.sh   <-- run here
  graphs/               decision graphs (gold exemplars + generated)
geophyto_qa.jsonl       the built dataset (1,505 items: 1,453 Lane A + 52 Lane B)
BugWood_Diseases_enriched.csv   source disease table (host, disease, state, sci-name)
GEOPHYTO_QA_README.md   full pipeline design + per-step I/O contracts
docs/                   design notes, paper outline, decision-graph source
```

> Heavy third-party inputs (WorldClim/Köppen rasters, PlantVillage, raw Bugwood
> tables) are **not** in this repo — see [Data & attribution](#data--attribution).

## Step-by-step data curation

The simplest linear recipe (each step = one SLURM file in `geophyto_qa/slurm/`):

| # | step | command (module) | output |
|---|------|------------------|--------|
| 0 | source table | *(provided)* `BugWood_Diseases_enriched.csv` | host/disease/state/sci-name rows |
| 1 | mine pairs | `geophyto_qa.mine_pairs` | `pairs/candidates.json` |
| 2 | web-confirm look-alikes ⚙ | `geophyto_qa.lookalike.gen_sweep_workflow` → Workflow → `persist_sweep` | `lookalike/web_evidence.json` |
| 3 | CLIP route (GPU) | `geophyto_qa.lookalike.clip_confuse` | `lookalike/clip_scores.json` |
| 4 | confirm + lane | `geophyto_qa.lookalike.verify_pairs` | `lookalike/confirmed_lookalikes.json` |
| 5 | author graphs ⚙ | `geophyto_qa.gen_lay_workflow` → Workflow → `persist_lay` | `graphs/generated/*.json` |
| 6 | VLM labels (GPU) | `geophyto_qa.lookalike.vlm_label` | `lookalike/vlm_labels.json` |
| 7 | **build** | `geophyto_qa.build` | **`geophyto_qa.jsonl`** |
| 8 | prior audit | `geophyto_qa.audit.{resolve_pathogens,research_ranges,score_prior,apply_audit}` | `audit/prior_audit.json` |
| 9 | rebuild + check | `geophyto_qa.build --corrections …` ; `geophyto_qa.audit.check_splits` | corrected `geophyto_qa.jsonl` |

⚙ = LLM/web step run through the Claude Code Workflow engine (generates a script, you
execute it, then a `persist_*` step writes results). All others are plain batch jobs.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install numpy requests                 # CPU steps (mine/identify/verify/build/audit)
pip install torch open_clip_torch          # S04  CLIP router (GPU)
pip install vllm transformers pillow       # S07  per-image VLM labels (GPU)
# S03 / S06 / S10 drive the `claude` CLI with web access (LLM/web steps)
```

## Quickstart — use the dataset

The built benchmark ships in `geophyto_qa.jsonl` (one JSON object per line):

```bash
python - <<'PY'
import json
rows = [json.loads(l) for l in open("geophyto_qa.jsonl")]
print(len(rows), "items")
it = rows[0]
print("lane:", it["lane"], "| split:", it["split"])
for t in it["dialogue"]: print(f'  [{t["turn"]}] {t["speaker"]}: {t["text"]}')
print("gold:", it["gold"]["diagnosis"], "| ruled_out:", it["gold"]["ruled_out"])
PY
```

Each item carries: `image` (Bugwood URL + attribution), `grounding`, `dialogue`
(F1–F4 / E1–E4), grounded `cot[]`, `gold`, a `counterfactual` region swap, the
`lookalike.evidence` (web quote + CLIP lane), and its `split`.

## Running it

Two entry points. Every job writes `geophyto_qa/logs/<step>_%j.{out,err}`.

### A. 10-sample smoke run (one batch, ~1 min, no GPU/LLM)

Sanity-check the whole deterministic path on 10 items, reusing the upstream
artifacts already in the repo (confirmed pairs + graphs + VLM labels). Writes to
`*_smoke10.*`, so the real dataset is untouched.

```bash
sbatch geophyto_qa/slurm/run_smoke10.slurm
# -> builds geophyto_qa_smoke10.jsonl (10 items) + runs resolve -> score -> split-check
```

Or run it inline without SLURM:

```bash
python -m geophyto_qa.build --csv BugWood_Diseases_enriched.csv --min-imgs 12 \
    --seed 20260613 --max 10 --report --out geophyto_qa_smoke10.jsonl
python -m geophyto_qa.audit.check_splits --jsonl geophyto_qa_smoke10.jsonl
```

### B. Full sweep (full dataset)

Every step is **one command = one `.slurm` file** in `geophyto_qa/slurm/`, run in order:

```bash
# --- build the dataset (Phase A–C) ---
sbatch geophyto_qa/slurm/step01_mine_pairs.slurm
sbatch geophyto_qa/slurm/step02_identify_pairs.slurm
#  S03 web-confirm + S06 graph-gen only GENERATE a Workflow script that you then run
#  in the Claude Code Workflow engine (see geophyto_qa/slurm/README.md) — not pure batch.
sbatch geophyto_qa/slurm/step03_web_confirm_gen.slurm   # -> Workflow -> persist_sweep
sbatch geophyto_qa/slurm/step04_clip_sweep.slurm        # GPU
sbatch geophyto_qa/slurm/step05_verify_pairs.slurm
sbatch geophyto_qa/slurm/step06_graph_gen.slurm         # -> Workflow -> persist_lay
sbatch geophyto_qa/slurm/step07_vlm_label.slurm         # GPU
sbatch geophyto_qa/slurm/step08_build.slurm             # -> geophyto_qa.jsonl

# --- prior-validation audit + corrected rebuild (Phase D–F) ---
bash geophyto_qa/slurm/submit_audit_chain.sh            # S09 -> S10 -> S11 -> S12 -> S15 -> S16
```

The full step table (nodes, I/O contracts, dependency DAG) is in
**[`GEOPHYTO_QA_README.md`](GEOPHYTO_QA_README.md)** and
**[`geophyto_qa/slurm/README.md`](geophyto_qa/slurm/README.md)**.

## Prior-validation audit (Phase D)

Lane-B gold trusts a contributor-count regional prior. The audit checks it against
an **independent, citation-based** external range signal (authoritative
extension / USDA / APS range statements — deliberately **not** GBIF or any other
collection count, which would share Bugwood's sampling bias):

```
S09 resolve_pathogens  ->  107 pathogens, pair-claims
S10 research_ranges    ->  cited US range per pathogen (claude CLI)
S11 score_prior        ->  agree / flip / non_discriminative / undetermined
S12 apply_audit        ->  Lane-B corrections (keep / relabel / drop / flag)
S15 build --corrections->  corrected dataset
```

`non_discriminative` (both diseases co-occur in the region) is the key verdict: it
means geography *cannot* break the tie, so the Lane-B premise fails for that pair.

## Determinism

All builds use `--seed 20260613` and self-check every item (must print `PASS`).

## Data & attribution

- Images are hosted by **Bugwood.org** under **per-image CC licenses**; the dataset
  references image URLs + attribution, it does not redistribute the images.
- Range statements cite extension / USDA / APS / university sources (quoted with URLs).
- Heavy inputs (WorldClim 2.1, Köppen-Geiger, PlantVillage, raw Bugwood tables) are
  excluded from this repo and subject to their own licenses.

*No code license is set yet (defaults to all-rights-reserved). Add a `LICENSE` if you
want to permit reuse.*
