"""
Generate the full-sweep Workflow script with the top-N candidate pairs embedded
as a JS const (Workflow scripts cannot read files). The workflow pipelines each
pair through web-verification then (if web-verified) decision-graph generation.

Usage:  python -m geophyto_qa.lookalike.gen_sweep_workflow --top 120 \
            --out geophyto_qa/lookalike/sweep_workflow.js
"""
from __future__ import annotations
import argparse, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)


def slim(p):
    return {"pair_id": p["pair_id"], "crop": p["crop"],
            "a": p["member_a"]["disease"], "b": p["member_b"]["disease"],
            "a_sci": p["member_a"].get("path_sci", ""),
            "b_sci": p["member_b"].get("path_sci", ""),
            "shared": p.get("shared_descriptors", [])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default=os.path.join(PKG, "pairs", "candidates.json"))
    ap.add_argument("--top", type=int, default=120)
    ap.add_argument("--from-clip", default=None,
                    help="clip_scores.json: restrict the sweep to image-confusable pairs (level-1 survivors)")
    ap.add_argument("--out", default=os.path.join(HERE, "sweep_workflow.js"))
    args = ap.parse_args()

    pairs = json.load(open(args.pairs))["pairs"]
    if args.from_clip:
        ok = {p for p, c in json.load(open(args.from_clip))["scores"].items()
              if c.get("image_confusable")}
        pairs = [p for p in pairs if p["pair_id"] in ok]   # keep prior-rank order
        print(f"restricting to {len(pairs)} image-confusable (level-1) pairs")
    else:
        pairs = pairs[:args.top]
    cands = [slim(p) for p in pairs]
    cand_js = json.dumps(cands)

    js = r'''export const meta = {
  name: 'geophyto-lookalike-sweep',
  description: 'Full-sweep web-verify + decision-graph generation for candidate look-alike disease pairs',
  phases: [ { title: 'Web' }, { title: 'Graph' } ],
}

const CANDIDATES = __CANDS__
const CREDIBLE = new Set(['extension', 'university', 'peer_reviewed', 'gov'])

const WEB_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['pair_id','confusable_documented','quote','source_url','source_title','source_type','confidence'],
  properties: {
    pair_id: { type: 'string', description: 'echo the exact pair_id you were given' },
    confusable_documented: { type: 'boolean', description: 'true only if a credible source states the two are confused / look alike / hard to distinguish' },
    quote: { type: 'string', description: 'verbatim snippet from the source supporting confusion (empty if none)' },
    source_url: { type: 'string' },
    source_title: { type: 'string' },
    source_type: { type: 'string', enum: ['extension','university','peer_reviewed','gov','other'] },
    confidence: { type: 'string', enum: ['high','medium','low'] },
  },
}

const FORK_AXES = ['growth_stage','plant_part','symptom_class','progression','sign_vector','environment','morphology','habit']
const GRAPH_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['pair_id','confusable','confusable_reason','shared_presentation','forks','narrative_a','narrative_b','management_a','management_b','geo_localizable_a','geo_localizable_b'],
  properties: {
    pair_id: { type: 'string', description: 'echo the exact pair_id you were given' },
    confusable: { type: 'boolean' },
    confusable_reason: { type: 'string' },
    shared_presentation: { type: 'string' },
    forks: { type: 'array', minItems: 3, maxItems: 7, items: {
      type: 'object', additionalProperties: false,
      required: ['axis','question','a_signal','b_signal','weight'],
      properties: {
        axis: { type: 'string', enum: FORK_AXES },
        question: { type: 'string' },
        a_signal: { type: 'string', description: 'observation leaning to member_a' },
        b_signal: { type: 'string', description: 'observation leaning to member_b' },
        weight: { type: 'string', enum: ['weak','supporting','decisive'] },
      } } },
    narrative_a: { type: 'string' }, narrative_b: { type: 'string' },
    management_a: { type: 'string' }, management_b: { type: 'string' },
    geo_localizable_a: { type: 'boolean' }, geo_localizable_b: { type: 'boolean' },
  },
}

function webPrompt(c) {
  return `You are a US extension plant pathologist. Determine whether "${c.a}" and "${c.b}" on ${c.crop} `
    + `are DOCUMENTED look-alikes — commonly confused, hard to tell apart, or explicitly compared — `
    + `according to credible US sources (cooperative extension .edu, university, peer-reviewed, USDA). `
    + `Search the web. If a credible source states or clearly implies the two are confused / similar / `
    + `look alike, set confusable_documented=true and return a VERBATIM quote plus its source URL and title `
    + `and the source_type. If you cannot find such a source, set confusable_documented=false with an empty quote. `
    + `Do NOT fabricate; only report what a real page says. Set pair_id to exactly "${c.pair_id}".`
}

function graphPrompt(c) {
  return `You are a US extension plant pathologist building a diagnostic DECISION GRAPH to tell apart two `
    + `LOOK-ALIKE diseases on the same crop. Branch only on observable evidence using these axes: `
    + `growth_stage, plant_part, symptom_class, progression, sign_vector (pathogen signs/vector), environment, `
    + `morphology, habit. Use 3-7 forks ordered coarse->fine; EXACTLY ONE fork has weight "decisive" (the single `
    + `observation that resolves the pair on its own, e.g. split the stem / flip the leaf / examine the sign). `
    + `a_signal always describes member_a, b_signal member_b. geo_localizable_x=true only if that disease's `
    + `likelihood depends on US region/season (false if nationwide). If they are not truly confused, set `
    + `confusable=false.\n\n`
    + `CROP: ${c.crop}\nMEMBER_A: ${c.a} (${c.a_sci})\nMEMBER_B: ${c.b} (${c.b_sci})\n`
    + `Set pair_id to exactly "${c.pair_id}". member_a is ${c.a}; member_b is ${c.b}. Return only the JSON object.`
}

const out = await pipeline(
  CANDIDATES,
  (c) => agent(webPrompt(c), { label: `web:${c.pair_id}`, phase: 'Web', schema: WEB_SCHEMA })
            .then((w) => ({ ...c, web: w })),
  (cw) => {
    const w = cw.web || {}
    const verified = !!(w.confusable_documented && CREDIBLE.has(w.source_type) && w.quote && w.quote.trim())
    if (!verified) return { pair_id: cw.pair_id, crop: cw.crop, a: cw.a, b: cw.b, web: w, verified: false, graph: null }
    return agent(graphPrompt(cw), { label: `graph:${cw.pair_id}`, phase: 'Graph', schema: GRAPH_SCHEMA })
      .then((g) => ({ pair_id: cw.pair_id, crop: cw.crop, a: cw.a, b: cw.b, web: w, verified: true, graph: g }))
      .catch(() => ({ pair_id: cw.pair_id, crop: cw.crop, a: cw.a, b: cw.b, web: w, verified: true, graph: null }))
  },
)

const results = out.filter(Boolean)
const verified = results.filter((r) => r.verified)
const graphed = verified.filter((r) => r.graph)
log(`web-verified ${verified.length}/${results.length}; graphs authored ${graphed.length}`)
return { n: results.length, n_verified: verified.length, n_graphed: graphed.length, results }
'''
    js = js.replace("__CANDS__", cand_js)
    with open(args.out, "w") as fh:
        fh.write(js)
    print(f"wrote {args.out} with {len(cands)} candidate pairs (top {args.top})")


if __name__ == "__main__":
    main()
