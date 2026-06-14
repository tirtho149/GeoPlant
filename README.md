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
geophyto_qa/            the package
  mine_pairs.py         candidate look-alike pairs
  lookalike/            confirmation (web gate) + CLIP router + per-image VLM labels
  graphgen.py schema.py decision-graph authoring + validation
  geo_oracle.py         contributor-de-biased regional prior
  render_two_lane.py    two-lane dialogue/CoT renderer
  build.py              assemble dataset + self-check
  audit/                Phase D prior validation (resolve / research / score / apply)
  slurm/                one .slurm per step + submit_audit_chain.sh   <-- run here
graphs/                 decision graphs (gold exemplars + generated)
geophyto_qa.jsonl       the built dataset (4,956 items)
GEOPHYTO_QA_README.md   full pipeline design + per-step I/O contracts
```

> Heavy third-party inputs (WorldClim/Köppen rasters, PlantVillage, raw Bugwood
> tables) are **not** in this repo — see [Data & attribution](#data--attribution).

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

## Running the full pipeline

Every step is **one command = one `.slurm` file** in `geophyto_qa/slurm/`
(full dataset). Submit from the repo root; logs land in `geophyto_qa/logs/`.

```bash
# build the dataset (Phase A–C)
sbatch geophyto_qa/slurm/step01_mine_pairs.slurm
sbatch geophyto_qa/slurm/step02_identify_pairs.slurm
#  S03 web-confirm + S06 graph-gen generate a Workflow script that you then run in
#  the Claude Code Workflow engine (see geophyto_qa/slurm/README.md) — not pure batch.
sbatch geophyto_qa/slurm/step04_clip_sweep.slurm      # GPU
sbatch geophyto_qa/slurm/step05_verify_pairs.slurm
sbatch geophyto_qa/slurm/step07_vlm_label.slurm       # GPU
sbatch geophyto_qa/slurm/step08_build.slurm

# prior-validation audit + corrected rebuild (Phase D–F), chained with afterok deps:
bash geophyto_qa/slurm/submit_audit_chain.sh          # S09 -> S10 -> S11 -> S12 -> S15 -> S16
```

Or run a step directly without SLURM, e.g.:

```bash
python -m geophyto_qa.build --csv BugWood_Diseases_enriched.csv --min-imgs 12 \
    --seed 20260613 --report --out geophyto_qa.jsonl
python -m geophyto_qa.audit.check_splits --jsonl geophyto_qa.jsonl
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
