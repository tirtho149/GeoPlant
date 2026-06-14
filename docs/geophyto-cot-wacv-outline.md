# GeoPhyto-CoT — WACV-style Paper & Dataset Outline
### A Long-Context Chain-of-Thought Benchmark for Ecological Geolocation of Plant-Disease Imagery

*(working title / placeholder name)*

---

## 0. One-line framing
The first benchmark where a model, given a **plant-disease image**, must reason
to **where it was taken** — not classify the disease. Because a symptom
close-up has no street-view cues, location must be inferred through *ecological*
reasoning (host + disease → plausible geography), making this a new kind of
geolocation task.

---

## 1. Abstract (½ column)
- Problem: VLMs are tested on disease *classification* or on street-view
  *geolocation*; neither asks a model to locate a plant-disease image.
- Gap: symptom close-ups lack visual geo-cues, so existing geolocation methods
  fail; location signal lives in host range + pathogen distribution.
- Contribution: GeoPhyto-CoT — N geo-tagged plant-disease images (from Bugwood)
  with long-context, multi-step CoT QA whose answer is a location at tiered
  granularity, plus a benchmark and baselines showing current VLMs underperform.
- Result headline: best VLM reaches only X% country-level accuracy; reasoning
  faithfulness lags; fine-tuning on the train split improves by Y%.

---

## 2. Introduction
- Motivation: biosecurity / outbreak provenance / "where could this have come
  from?" is an ecological-reasoning question, not a recognition one.
- Why it's hard & novel: contrast **visual geolocation** (signs, architecture,
  vegetation) with **ecological geolocation** (host species range, pathogen
  distribution, climate suitability). Lead figure: a leaf close-up next to a
  GeoGuessr street scene — one has cues, one doesn't.
- Contributions (bulleted):
  1. A new task: ecological geolocation of plant-disease imagery.
  2. GeoPhyto-CoT dataset: geo-tagged images + long-context CoT QA, location-as-target.
  3. A faithfulness-aware evaluation protocol separating *reasoning* from *recall*.
  4. Benchmarking of M proprietary + open VLMs, plus a fine-tuned baseline and ablations.

---

## 3. Related Work
- **Plant-disease VQA / VLM benchmarks** (CDDM, AgMMU, PlantWild, LeafNet/LeafBench,
  AgroCoT) — all target diagnosis/management; location is never the answer.
- **Image geolocation reasoning** (GAEA, GeoChain, Geo-R1/IMAGEO-Bench, "Where on
  Earth?") — right task & CoT format, but visual-cue driven, general domain.
- **Species range / SDM + language** (iNaturalist SINR geo-prior, GeoPlant,
  "From Images to Insights") — closest reasoning skeleton (image→species→range),
  but outputs habitat explanations, not a disease geolocation QA benchmark.
- Position GeoPhyto-CoT at the intersection none of the above occupies.

---

## 4. Dataset Construction
### 4.1 Source & scope
- Bugwood Image Database; start from 20K geo-tagged records.
- **Filtering to plant + disease:** keep host = plant AND agent = disease
  (fungal/bacterial/viral/nematode); drop insect-subject, animal, weed-only,
  healthy. Report surviving count and the filter rules.
### 4.2 Ground-truth metadata (per image)
- image, license, attribution; host species (sci/common); disease (sci/common);
  geo-tag (lat/lon, country, admin1/2, locality); date; climate zone (Köppen,
  derived from lat/lon).
### 4.3 Corpus-derived geographic prior (Bugwood-only)
- Aggregate geo-tags **per disease and per host** to get an empirical
  distribution — this replaces external databases for v1.
- **Critical:** priors computed from the **training split only** to avoid turning
  the benchmark into a recall test.
### 4.4 QA generation pipeline
- Template + LLM-assisted generation of CoT chains from existing labels
  (host/disease are ground truth, so chains are grounded, not hallucinated).
- 6-step reasoning chain: PERCEIVE → IDENTIFY_HOST → DIAGNOSE_AGENT →
  GEO_PRIOR (corpus) → NARROW (climate/cues) → CONCLUDE (+ uncertainty).
- Each step cites a ground-truth field or the image (faithfulness gate).
### 4.5 Question taxonomy
| type | output | tests |
|------|--------|-------|
| geoloc_direct | location @ tier | end-to-end |
| geoloc_reasoning | full CoT + location | faithful chain |
| constraint_check | yes/no + justification | evidence weighing |
| counterfactual_negative | why a region is implausible | anti-shortcut |
| range_classification | native vs introduced | invasion reasoning |
| conversational_turn | multi-turn → location | long context |
### 4.6 Quality control
- Expert spot-check (stratified by host family / continent); reject ungrounded
  steps; verify CONCLUDE ∈ GEO_PRIOR candidate set.

---

## 5. Dataset Analysis (the "stats" section + figures)
- Totals: #images, #QA, #unique diseases, #unique hosts, #countries/regions.
- **Granularity tiers** and how each image is assigned a feasible answer tier
  (point / admin1 / country / climate-zone / range-class). Honest ceiling for
  close-ups is usually country / climate-zone.
- Geographic & taxonomic coverage maps; long-tail distribution of disease×region.
- **Locations-per-disease histogram** — diseases spanning ≥k regions are the
  reasoning-capable subset; single-region diseases flagged as recall-only.
- Split design: (a) random, (b) **held-out regions**, (c) **held-out species**.

---

## 6. Benchmark & Evaluation Protocol
- **Localization metrics:** accuracy @ country / admin1 / climate-zone; geodesic
  distance error (median km, % within {25,200,750,2500} km à la GeoGuessr).
- **Reasoning faithfulness:** step-grounding rate; chain consistency
  (CONCLUDE inside GEO_PRIOR); LLM-judge chain-quality score.
- **Anti-shortcut metric:** accuracy gap between in-distribution and
  held-out-region splits (smaller = real reasoning).
- **Conversational:** multi-turn answer correctness / context retention.

---

## 7. Experiments
- **Zero-shot VLMs:** GPT-4o/latest, Claude, Gemini, Qwen2.5-VL, InternVL,
  LLaVA-OneVision; plus geolocation-specialist GAEA-7B and ag-model AgroGPT.
- **Fine-tuned baseline:** train on the train split (LoRA), evaluate on held-out
  region/species.
- **Ablations:**
  - CoT vs. direct answer.
  - With vs. without corpus geo-prior in the prompt (long-context value).
  - Granularity sensitivity (does accuracy collapse below country level?).
  - Host-label-given vs. host-must-be-inferred.

---

## 8. Results & Analysis
- Main table: all models × all metrics × three splits.
- Key claims to support: (i) VLMs are weak at ecological geolocation; (ii) CoT +
  corpus prior helps; (iii) big in-distribution→held-out drop exposes reliance on
  recall; (iv) faithfulness ≠ accuracy (models get location right via wrong chains).
- Qualitative figure: a correct-answer / unfaithful-chain example.

---

## 9. Limitations & Ethics
- v1 uses corpus-derived priors only (no external distribution DBs) → coverage
  bounded by Bugwood's geography (likely US/North-America heavy); state this.
- Geolocation of organisms raises misuse considerations; data is non-sensitive
  plant disease, but note responsible-use framing.
- **Licensing:** Bugwood images are per-image CC (BY / BY-NC), photographers
  retain rights; release QA + image IDs/URLs and preserve attribution rather than
  rehosting restricted images.

---

## 10. Conclusion
- Reframes geolocation as ecological reasoning; releases the first
  location-as-target plant-disease QA benchmark; shows headroom for VLMs.

---

## Appendix / Supplementary
- Full prompt templates for CoT generation and the LLM judge.
- Per-tier granularity assignment rules.
- Datasheet for Datasets (Gebru et al.) — provenance, licensing, splits.
- Additional qualitative chains; failure taxonomy.

---

### Open knobs to lock before writing
1. Final answer-granularity ceiling (country vs climate-zone as the headline tier).
2. Dataset name.
3. Whether v1 stays strictly Bugwood-only or adds host range as the one
   "free" external signal later.
