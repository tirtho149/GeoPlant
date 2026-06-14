# GeoPhyto-QA — geography-aware look-alike diagnosis VQA

Each item is a **multi-turn, image-grounded farmer↔ag-expert dialogue** in which the
expert reasons through a **look-alike decision graph** to tell apart two confusable
plant diseases. The reasoning is **geography-aware**: region / season / local disease
pressure (a contributor-de-biased oracle) are what make the expert's answer correct.

> GeoPhyto-QA answers *which look-alike is it, and does geography support that* —
> diagnosis, not geolocation. Constraints: **Bugwood-only · USA-only · contributor-de-biased oracle.**

## Two lanes (the core design)

Every confirmed look-alike pair is routed into one of two lanes; the lane decides
what the item tests and how the counterfactual control behaves.

| Lane | CLIP cross-kNN | What decides | Geography role | Counterfactual |
|------|----------------|--------------|----------------|----------------|
| **A — `image_decisive`** | `< 0.20` (separable) | the **visible sign** in the photo | a **no-flip control**: swapping region must NOT change the answer | answer stays put |
| **B — `image_ambiguous`** | `≥ 0.20` (entangled) | **geography breaks the tie** (sign not separable in-pixel) | **load-bearing** | answer should flip when region flips |

Lane B is the novelty **and the risk**: its gold is only as trustworthy as the
regional prior. Validating that prior (Phase D) is the current critical path.

---

## Current state (tightened build of 2026-06-14)

- **`geophyto_qa.jsonl` — 1,505 items**, self-check **PASS**.
- Lanes: **Lane A (image_decisive) 1,453** · **Lane B (image_ambiguous) 52**.
- Splits: train 892 · test_random 167 · test_heldout_species 393 · test_heldout_region 53.
- Every Lane-B item now genuinely **flips** under region swap (0 Lane-B controls); no image spans two splits.

> **Why Lane B collapsed 3,503 → 52.** Tightening (below) keeps a Lane-B item only when
> *all* hold: CLIP says the pair is intrinsically entangled (`image_ambiguous`), the VLM
> says the deciding sign isn't visible in that photo, the distractor actually occurs on the
> photographed organ, **and** some region honestly favors the distractor (a real flip). The
> old Lane B was ~90% photo-quality ambiguity / organ-mismatch / fake flips. **52 is the
> honest count of "geography genuinely breaks the tie" in this corpus** — a key result for
> the paper decision (the geography novelty is small; the dataset is Lane-A-heavy).

### Known blockers (from review) — status
1. **Lane-B gold rides on an unvalidated prior** (contributor-counts, not epidemiology).
   → **Phase D** (S09/S11/S16 built & verified; S10 range-research pending — the LLM/web step).
2. **Invalid counterfactual swap** → **FIXED (S13)**: `geo_oracle.swap_to_distractor_region` only
   swaps to a region where the distractor genuinely beats the true member, else no-flip control.
3. **Decisive sign leaked into Lane-B text** (was 72%) → **FIXED (S14)**: removed from all Lane-B
   dialogue/CoT; survives only in hidden `gold.confirm_action`.
4. **Split leakage** (8 images) → **FIXED (S16)**: `build.make_splits` collapses to image level.
5. **Lane incoherence** (81% of old Lane B was CLIP-`image_decisive`; 44% organ-mismatched) →
   **FIXED**: build now drops Lane-B items that fail CLIP+VLM agreement, organ-compat, or can't flip.

---

## How to run — one `.slurm` per step, full dataset, in order

**The slurm files already exist** in `geophyto_qa/slurm/` (one per step) — see
`geophyto_qa/slurm/README.md` for the table. Submit from the repo root:

```bash
sbatch geophyto_qa/slurm/step01_mine_pairs.slurm        # ... step02, step04, ...
# or chain the automatable prior-audit + rebuild (S09→S16) with afterok deps:
bash  geophyto_qa/slurm/submit_audit_chain.sh
```

Each step below is **one command** = **one `.slurm` file**; logs land in
`geophyto_qa/logs/`. The step blocks below give the command each file runs (the
canonical contract); edit `--partition` / `--time` / `--mem` in the files per cluster.

Legend: **[CPU]** plain compute · **[GPU]** scavenger + `--gres=gpu:1` · **[LLM/web]**
drives the `claude` CLI · **[exists]** code in repo · **[DONE]** fix already applied.

> ⚠ **S03 and S06** are not pure batch jobs: the `.slurm` only *generates* the
> Workflow `.js`; the per-pair web-verify / graph-authoring runs in the Claude Code
> Workflow engine, then a `persist_*` step writes the results. `submit_audit_chain.sh`
> therefore chains only the deterministic Phase-D side (S09→S16).

---

### Phase A — Pairs & look-alike confirmation

**S01 — mine candidate pairs** · [CPU] [exists]
Within-crop confusable pairs, ranked by a cheap prior (candidacy only).
```bash
python -m geophyto_qa.mine_pairs --csv BugWood_Diseases_enriched.csv --min-imgs 12 \
    --out geophyto_qa/pairs/candidates.json
```
out → `pairs/candidates.json`

**S02 — identify all pairs (reproducible manifest)** · [CPU] [exists]
Mines every candidate, joins existing web+CLIP evidence, emits the work-list.
```bash
python -m geophyto_qa.lookalike.identify_pairs --csv BugWood_Diseases_enriched.csv \
    --min-imgs 12 --out-dir geophyto_qa/pairs
```
out → `pairs/pair_manifest.json`, `pairs/needs_web.json`

**S03 — THE GATE: web-confirm look-alikes** · [LLM/web] [exists: `web_verify.py` store + `*_workflow.js` drivers]
For every pair in `needs_web.json`, record a credible source quote+URL stating the two
are confused. A pair is a dataset look-alike **iff** this passes. Run your agent/workflow
driver over the full work-list; it writes through `web_verify.record(...)`.
```bash
# full-dataset driver (CLI/agent) -> appends to web_evidence.json
python -m geophyto_qa.lookalike.gen_sweep_workflow --all   # emits sweep_workflow_full.js to execute
```
out → `lookalike/web_evidence.json`

**S04 — THE ROUTER: CLIP cross-kNN sweep** · [GPU] [exists]
Embeds each class's Bugwood photos, scores cross-kNN entanglement → lane hint per pair.
(Existing `clip_sweep.sbatch` is exactly this step.)
```bash
python -m geophyto_qa.lookalike.clip_confuse --per-class 40 --knn-thresh 0.12 \
    --out geophyto_qa/lookalike/clip_scores.json
```
out → `lookalike/clip_scores.json`

**S05 — apply gate + router** · [CPU] [exists]
`confirmed = web`; `clip_lane_hint` (Lane A/B) = CLIP. CLIP never vetoes.
```bash
python -m geophyto_qa.lookalike.verify_pairs \
    --web geophyto_qa/lookalike/web_evidence.json \
    --clip geophyto_qa/lookalike/clip_scores.json \
    --out geophyto_qa/lookalike/confirmed_lookalikes.json
```
out → `lookalike/confirmed_lookalikes.json`

### Phase B — Graphs & per-image labels

**S06 — author a decision graph per confirmed pair** · [LLM/web] [exists: `graphgen.py` lib + workflow]
One discriminator graph per pair (3–7 forks, exactly one `decisive`), schema-validated.
Gold exemplars in `graphs/gold/`; generated graphs validated then saved.
```bash
# full-dataset driver: one LLM call per confirmed pair, schema-forced, then validate+save
python -m geophyto_qa.gen_lay_workflow --all   # emits the per-pair graphgen workflow to execute
```
out → `graphs/generated/*.json`

**S07 — per-image VLM lane labels** · [GPU] [exists]
Labels every Bugwood image (sign visible? → per-image lane), used by the renderer.
(Existing `vlm_label.sbatch` is this step; drop `--limit` for full dataset.)
```bash
python -m geophyto_qa.lookalike.vlm_label --cap 40 --out geophyto_qa/lookalike/vlm_labels.json
```
out → `lookalike/vlm_labels.json`

### Phase C — Build

**S08 — build the dataset (initial)** · [CPU] [exists]
Web-confirmed pairs that also have a validated graph → walk graph + image → dialogue,
CoT, gold, geo-oracle block, counterfactual, split. Self-checks every item (must print `PASS`).
```bash
python -m geophyto_qa.build --csv BugWood_Diseases_enriched.csv --min-imgs 12 \
    --seed 20260613 --report --out geophyto_qa.jsonl
```
out → `geophyto_qa.jsonl`, `geophyto_qa.coverage.json`

---

### Phase D — Prior validation (the load-bearing gate)

Validate the contributor-count regional prior against an **independent, citation-based**
external range signal (authoritative extension/USDA/APS *range statements* — NOT another
collection count like GBIF). Where the prior and the external source disagree, Lane-B gold
is wrong; where both members co-occur in the region, Lane B's premise itself fails.

**S09 — resolve pathogens & extract pair-claims** · [CPU] [exists: `geophyto_qa/audit/resolve_pathogens.py`]
Map every Lane-B `(host, disease)` → pathogen binomial via the enriched CSV's
`Scientific Name`, with host-alias + disease-level fallback (covers 107/107 pathogens; only
`watermelon/Unknown Virus` unresolvable). Emit the per-pair claim set the prior asserts.
```bash
python -m geophyto_qa.audit.resolve_pathogens --jsonl geophyto_qa.jsonl \
    --csv BugWood_Diseases_enriched.csv \
    --out-pathogens geophyto_qa/audit/pathogen_worklist.json \
    --out-claims    geophyto_qa/audit/pair_claims.json
```
out → `audit/pathogen_worklist.json` (107 binomials + context), `audit/pair_claims.json`
(every `(host, true, distractor, region)` Lane-B claim + the prior's stored weights)

**S10 — research US range per pathogen** · [LLM/web] [exists: `geophyto_qa/audit/research_ranges.py`]
For all 107 pathogens, gather a cited US range statement from authoritative sources
(extension `.edu` / USDA / APS / CABI). One record per pathogen: `regions_present`,
`regions_core` (severe/endemic), `cosmopolitan`, verbatim `quote`, `source_url`,
`confidence`. Driver fans out one LLM-with-web call per pathogen and merges results.
Mirrors the `web_verify.py` evidence-store pattern.
```bash
python -m geophyto_qa.audit.research_ranges --worklist geophyto_qa/audit/pathogen_worklist.json \
    --out geophyto_qa/lookalike/web_range_evidence.json
```
out → `lookalike/web_range_evidence.json` (2 entries already seeded: CDM, cucumber anthracnose)

**S11 — score the prior** · [CPU] [exists: `geophyto_qa/audit/score_prior.py`]
For each pair-claim, compare the prior's "region favors TRUE" against the range evidence.
Verdicts: **agree** (true present, distractor absent in region) · **flip** (distractor
present, true absent → *mislabeled gold*) · **non_discriminative** (both co-occur → *Lane B
premise fails for this pair*) · **undetermined** (no credible range info). Reports coverage so
"no flips" can't masquerade as "prior valid". (Drop the GBIF backend; read `web_range_evidence.json`.)
```bash
python -m geophyto_qa.audit.score_prior --claims geophyto_qa/audit/pair_claims.json \
    --ranges geophyto_qa/lookalike/web_range_evidence.json \
    --out geophyto_qa/audit/prior_audit.json
```
out → `audit/prior_audit.json` (per-pair verdicts + agree/flip/non_discriminative/undetermined summary)

**S12 — apply the audit (regold / drop)** · [CPU] [exists: `geophyto_qa/audit/apply_audit.py`]
Turn verdicts into actions: `flip` → relabel or drop the pair's Lane-B items; `non_discriminative`
→ demote out of Lane B (geography can't decide) or drop; `agree` → keep. Writes a corrected
pair/gold table that the rebuild (S15) consumes. Nothing dropped silently — logs every action.
```bash
python -m geophyto_qa.audit.apply_audit --audit geophyto_qa/audit/prior_audit.json \
    --out geophyto_qa/audit/lane_b_corrections.json
```
out → `audit/lane_b_corrections.json`

---

### Phase E — Integrity fixes (landed in code; take effect on the S15 rebuild)

**S13 — counterfactual swap** · [DONE: `geo_oracle.py` + `render_two_lane.py`]
`swap_to_distractor_region(true, distractor)` now picks a region where the **distractor is
genuinely more plausible than the true member** (per the de-biased prior); if no region
favors the distractor, the item is emitted as a **no-flip control** instead of a bogus shift.
*No separate run — applied by the S15 rebuild.*

**S14 — text-level sign leakage in Lane B** · [DONE: `render_two_lane.py`]
The decisive-sign wording is removed from every Lane-B dialogue/CoT turn (replaced with
"the one feature that would separate them isn't readable in this image" + a hands-on-check
prompt); the specific sign survives **only** in the hidden `gold.confirm_action`.
*Applied by the S15 rebuild; verify with the leakage probe (should drop from 72% → ~0%).*

### Phase F — Rebuild & verify

**S15 — rebuild with corrections** · [CPU] [exists, after S12–S14 land]
```bash
python -m geophyto_qa.build --csv BugWood_Diseases_enriched.csv --min-imgs 12 \
    --seed 20260613 --report --out geophyto_qa.jsonl
```
out → corrected `geophyto_qa.jsonl` + `geophyto_qa.coverage.json` (self-check must print `PASS`)

**S16 — split hygiene check** · [CPU] [exists: `geophyto_qa/audit/check_splits.py`; fix in `build.make_splits`]
Asserts no `image_number` spans two splits (the 8 train↔test_random leaks are fixed in
`build.make_splits`, which now collapses splits to image level) and reports split sizes.
Exits non-zero if any image leaks — use it to gate the pipeline.
```bash
python -m geophyto_qa.audit.check_splits --jsonl geophyto_qa.jsonl
```
out → console report (fails non-zero if any image leaks across splits)

---

## Dependency order (DAG)

```
S01 → S02 → S03 ┐
            S04 ┴→ S05 → S06 → S07 → S08 ─┐
                                          │
S08 → S09 → S10 → S11 → S12 ──────────────┤
                                          ├→ S15 → S16
       S13 (render) ──────────────────────┤
       S14 (render) ──────────────────────┘
```
S03/S04 are independent (run in parallel). S09–S12 (prior audit) and S13–S14 (render fixes)
are independent of each other; both must finish before the corrected rebuild S15.

## Data artifacts

| file | produced by | role |
|------|-------------|------|
| `BugWood_Diseases_enriched.csv` | (upstream `geoplant/`) | source rows; carries `Scientific Name` |
| `pairs/{candidates,pair_manifest,needs_web}.json` | S01–S02 | pair work-lists |
| `lookalike/web_evidence.json` | S03 | look-alike confirmation gate (quote+URL) |
| `lookalike/clip_scores.json` | S04 | CLIP cross-kNN → lane router |
| `lookalike/confirmed_lookalikes.json` | S05 | confirmed pairs + lane |
| `graphs/{gold,generated}/*.json` | S06 | per-pair decision graphs |
| `lookalike/vlm_labels.json` | S07 | per-image lane labels |
| `geophyto_qa.jsonl` / `.coverage.json` | S08, S15 | the dataset + coverage report |
| `audit/pathogen_worklist.json`, `audit/pair_claims.json` | S09 | resolved pathogens + prior claims |
| `lookalike/web_range_evidence.json` | S10 | **external cited range statements** |
| `audit/prior_audit.json` | S11 | per-pair prior verdicts |
| `audit/lane_b_corrections.json` | S12 | regold/drop actions |

## What gates the paper

The contributor-count prior is the one load-bearing assumption not yet shown true.
**Phase D decides it.** If the `non_discriminative` + `flip` rate over Lane B is high,
the regional axis is largely non-informative for these co-distributed humid-eastern
pathogens and Lane B must be re-grounded (or the paper leans on Lane A + a smaller,
audited Lane B). Phases E–F make every other reviewer objection (invalid swap, text
leakage, split leakage) go away.

## Notes / deprecated

- **Cleaned 2026-06-14** → `_archive/`: the GBIF prototype (`audit_prior.py`, `gbif_ranges.json`,
  `fetch_gbif_ranges.py`, `gbif_range.py`, `gee.py`), alternate-direction builds
  (`scripts/build_geo_qa.py`, `build_geo_vqa.py`), backups/logs/smoke artifacts. GBIF is a
  collection count (same bias family as Bugwood) and is **not used** — S10/S11 use the
  citation-based range backend instead.
- Determinism: all builds use `--seed 20260613`. The build self-checks every item (prints `PASS`).
- Per-image CC licensing: release dialogues + Bugwood image IDs with attribution.
```
