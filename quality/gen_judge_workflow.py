"""
Generate a Workflow that runs tirtho149/SAGE SageQualityChecker/disease_label_judge.py
prompts (Layer 1 crop validation + Layer 2 disease-label judge) over the Bugwood
crop/disease registry — one agent per crop, schema-forced. Faithful to the
original prompts; just parallelised. Output is reassembled into the original
disease_label_full_report.json shape by apply_judge.py.

  python quality/gen_judge_workflow.py --out quality/judge_workflow.js
"""
import argparse, csv, collections, json, os
HERE = os.path.dirname(os.path.abspath(__file__))

CROP_PROMPT = r"""You are an expert agronomist. Apply the decision tree below to the crop name given.

DECISION TREE:
  Node A: Is this entry a real plant or plant-based crop (not a spreadsheet label, number, or non-plant)?
    -> NO  -> verdict: INVALID
    -> YES -> Node B
  Node B: Is it grown as an agricultural or horticultural crop (food, fibre, spice, timber, ornamental)?
    -> NO  -> verdict: NON_CROP
    -> YES -> Node C
  Node C: Is the common crop name spelled correctly and reasonably standardised?
    -> NO  -> verdict: MISSPELLED_OR_UNSTANDARDISED
    -> YES -> verdict: VALID"""

DIS_PROMPT = r"""You are an expert plant pathologist. Quality-check disease labels for the crop below.

Verdict rules:
  CORRECT      - well-documented disease known to affect this crop.
  INCORRECT    - wrong crop; disease of a completely different plant; or entry is not a disease at all.
  QUESTIONABLE - real disease but label is vague, misspelled, names a pathogen genus instead of a
                 disease, refers to an insect pest or beneficial organism, or is an unusual
                 / unverified association with this crop."""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", default=os.path.join(HERE, "crop_disease_registry.csv"))
    ap.add_argument("--out", default=os.path.join(HERE, "judge_workflow.js"))
    args = ap.parse_args()

    bycrop = collections.defaultdict(list)
    for row in csv.DictReader(open(args.registry)):
        if row["Disease"] not in bycrop[row["Crop"]]:
            bycrop[row["Crop"]].append(row["Disease"])
    crops = [{"crop": c, "diseases": ds} for c, ds in sorted(bycrop.items())]
    crops_js = json.dumps(crops)

    js = r'''export const meta = {
  name: 'disease-label-judge',
  description: 'SAGE two-layer crop/disease label quality check (Layer1 crop validity + Layer2 disease judge)',
  phases: [ { title: 'Judge' } ],
}

const CROPS = __CROPS__
const CROP_PROMPT = __CROP_PROMPT__
const DIS_PROMPT = __DIS_PROMPT__

const SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['crop','crop_validation','disease_check'],
  properties: {
    crop: { type: 'string' },
    crop_validation: {
      type: 'object', additionalProperties: false,
      required: ['node_a','node_b','node_c','verdict','canonical_name','category','notes'],
      properties: {
        node_a: { type: 'string', enum: ['YES','NO'] },
        node_b: { type: 'string', enum: ['YES','NO','N/A'] },
        node_c: { type: 'string', enum: ['YES','NO','N/A'] },
        verdict: { type: 'string', enum: ['VALID','INVALID','NON_CROP','MISSPELLED_OR_UNSTANDARDISED'] },
        canonical_name: { type: 'string' },
        category: { type: 'string' },
        notes: { type: 'string' },
      },
    },
    disease_check: {
      type: 'object', additionalProperties: false,
      required: ['disease_verdicts','similar_groups','summary'],
      properties: {
        disease_verdicts: { type: 'array', items: {
          type: 'object', additionalProperties: false,
          required: ['disease','verdict','reason'],
          properties: {
            disease: { type: 'string' },
            verdict: { type: 'string', enum: ['CORRECT','INCORRECT','QUESTIONABLE'] },
            reason: { type: 'string' },
          } } },
        similar_groups: { type: 'array', items: {
          type: 'object', additionalProperties: false,
          required: ['diseases','reason'],
          properties: {
            diseases: { type: 'array', items: { type: 'string' } },
            reason: { type: 'string' },
          } } },
        summary: { type: 'string' },
      },
    },
  },
}

function prompt(c) {
  const dl = c.diseases.map((d) => `- ${d}`).join('\n')
  return `${CROP_PROMPT}\n\nThen, for the SAME crop:\n\n${DIS_PROMPT}\n\n`
    + `Crop to evaluate: ${c.crop}\n\nDiseases:\n${dl}\n\n`
    + `Return the combined JSON object with crop, crop_validation (Layer 1), and disease_check (Layer 2).`
}

const out = await parallel(CROPS.map((c) => () =>
  agent(prompt(c), { label: `judge:${c.crop}`, phase: 'Judge', schema: SCHEMA })
    .then((r) => ({ ...r, crop: c.crop }))
    .catch(() => null)))

const results = out.filter(Boolean)
const inc = results.reduce((n, r) => n + (r.disease_check?.disease_verdicts || []).filter((v) => v.verdict === 'INCORRECT').length, 0)
const q = results.reduce((n, r) => n + (r.disease_check?.disease_verdicts || []).filter((v) => v.verdict === 'QUESTIONABLE').length, 0)
log(`judged ${results.length} crops; INCORRECT=${inc} QUESTIONABLE=${q}`)
return { n: results.length, results }
'''
    js = (js.replace("__CROPS__", crops_js)
            .replace("__CROP_PROMPT__", json.dumps(CROP_PROMPT))
            .replace("__DIS_PROMPT__", json.dumps(DIS_PROMPT)))
    open(args.out, "w").write(js)
    print(f"wrote {args.out} with {len(crops)} crops")


if __name__ == "__main__":
    main()
