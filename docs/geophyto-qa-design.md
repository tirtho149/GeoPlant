# GeoPhyto-QA — Long-Context Farmer↔Ag-Expert VQA
### Geography-aware plant-disease reasoning (no personas, no clinical framing)

Each item is a **multi-turn, image-grounded conversation** between a farmer and an
agricultural expert. The farmer shows a leaf and describes the situation
(including where they are); the expert reasons across turns to a diagnosis and
management answer, and the reasoning is **geography-aware** — region, season, and
local disease pressure are what make the expert's answers correct.

- **VQA:** every item is anchored on a real Bugwood leaf image; questions
  reference what's visible.
- **Long-context:** evidence accumulates over turns (image + location + weather +
  growth stage); the expert must integrate it, not answer turn-by-turn.
- **Geography enters as reported context**, not inferred from pixels — so the task
  is well-posed.

Constraints: Bugwood-only · USA-only · contributor-de-biased geographic oracle.

---

## 1. Item structure
```json
{
  "item_id": "gpqa-00412",
  "image": "bugwoodcloud.org/.../soybean_rust_uredinia.jpg",
  "license": "CC BY 3.0", "attribution": "<photographer>, Bugwood.org",
  "grounding": {                          // hidden from the model under test; used to build gold
    "host": "soybean (Glycine max)",
    "disease": "Asian soybean rust (Phakopsora pachyrhizi)",
    "region": "South / Cfa", "season_stage": "late / R3"
  },
  "geo_oracle": {                         // contributor-de-biased
    "plausible_regions": ["South"],
    "localizability": "localizable",
    "local_pressure": "rust active in region this season"
  },
  "dialogue": [ /* §3 */ ],
  "gold": { /* §4 */ }
}
```

## 2. How dialogues are built
Ground every dialogue in one real Bugwood case (image + host + disease + geo-tag)
plus the geo-oracle; generate the multi-turn farmer↔expert exchange (templates +
LLM drafting); then **validate with extension agronomists**. Season comes from
image-date metadata, climate (Köppen) from lat/lon.

## 3. The QA task
The model under test plays the **expert**: given the image and the farmer's turns,
it asks needed questions, reasons, and answers. Long-context because the location
given early must inform the answer later; VQA because answers must reference the
visible signs.

## 4. Evaluation
- **Answer correctness:** diagnosis + management vs gold.
- **Geographic consistency** (oracle-scored): expert uses region/season correctly
  to support or rule out; abstains from region claims when the disease is
  `cosmopolitan`.
- **Long-context integration:** does the expert use facts from earlier turns
  (location at turn 2 → answer at turn 4)?
- **VQA grounding / faithfulness:** reasoning cites visible signs + stated context.
- **Counterfactual region swap:** change only the farmer's stated location; the
  expert's answer should change for `localizable` diseases, stay put for
  `cosmopolitan` ones.

---

## 5. SAMPLE

### 5a. The long-context VQA dialogue
```
[F1] (image) My soybean lower leaves have tan-brown specks and they're dropping early. What is this?
[E1] Flip a lower leaf — do you see raised pustules on the underside? And where are you farming,
     and what stage are the beans?
[F2] Yes, little raised tan bumps underneath. I'm in Louisiana, beans are filling pods,
     it's been hot and humid with a lot of rain.
[E2] The underside pustules on lower, older leaves point to Asian soybean rust rather than
     Septoria brown spot, which looks similar but lacks those pustules. It fits your situation:
     the Gulf is where rust overwinters, and late-season humid weather drives it.
[F3] Will it spread? What should I do?
[E3] Yes — under warm, wet conditions it moves up the canopy fast. Scout the upper canopy now and
     apply a labeled fungicide at this reproductive stage; in the Gulf, regional pressure stays
     high once it's active, so don't wait.
[F4] My neighbor says it's just from the rain, nothing to worry about.
[E4] Rain is what favors it, not a reason to dismiss it. In your area this season rust is active
     and can defoliate quickly at pod-fill, so it's worth treating.
```

### 5b. Gold + scoring
```
diagnosis_gold:           Asian soybean rust
answer_correct:           ✓
geographic_consistency:   ✓  (uses Louisiana + late season + Gulf overwintering correctly)
long_context_integration: ✓  (location from F2 drives E2/E3; growth stage drives fungicide timing)
vqa_grounding:            ✓  (cites underside pustules + lower-canopy onset from the image)
```

### 5c. Counterfactual region swap
```
swap F2 location -> "Minnesota, early season"
expected expert shift: rust DEMOTED (no Gulf overwintering, unlikely early-season arrival);
                       Septoria brown spot / bacterial pustule promoted.
control (cosmopolitan disease, e.g. Septoria): swapping location should NOT change the answer.
```

---

## 6. Construction notes (USA-only)
- Geo-oracle = contributor-level aggregation + localizability gate over the 20K.
- `cosmopolitan` diseases retained as the control class for the swap, not discarded.

## 7. Limitations & ethics
- USA-only; geography = US region/climate, not global.
- Dialogues are constructed + agronomist-validated, not transcripts of real consultations.
- Geo-oracle bounded by Bugwood's contributor coverage.
- Per-image CC licensing; release dialogues + image IDs with attribution.
```
```
