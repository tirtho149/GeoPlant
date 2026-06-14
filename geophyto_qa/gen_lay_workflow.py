"""
Generate a Workflow that AUGMENTS each confirmed pair's existing (validated)
decision graph with a lay-language layer for the two-lane renderer:

  * farmer_lay_report : 1-2 sentences a grower would actually say about the
                        visible problem, with NO scientific jargon and NOT
                        naming either decisive sign (so it stays ambiguous).
  * decisive_lay_a/b  : each member's decisive sign in plain grower language
                        (what to look for), for the expert's image reading and
                        the "to confirm, check ..." guidance.
  * decisive_micro_a/b: true if that decisive sign is microscopic / needs a hand
                        lens or lab (so it usually can't be the image-decisive
                        cue) — a prior the VLM per-image label then confirms.

The existing forks/narratives are preserved; we only add `graph.lay`.

  python -m geophyto_qa.gen_lay_workflow --out geophyto_qa/lay_workflow.js
"""
from __future__ import annotations
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from geophyto_qa.build import graphs_by_pair, load_confirmed   # noqa: E402
from geophyto_qa.schema import decisive_fork                   # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "lay_workflow.js"))
    args = ap.parse_args()

    conf = load_confirmed(); graphs = graphs_by_pair()
    pairs = []
    for pid, d in conf.items():
        if not d.get("confirmed"):
            continue
        rec = graphs.get(pid)
        if not rec:
            continue
        g = rec["graph"]; fk = decisive_fork(g)
        if not fk:
            continue
        pairs.append({"pair_id": pid, "crop": d["crop"],
                      "a": d["member_a"], "b": d["member_b"],
                      "sign_a": fk["a_signal"], "sign_b": fk["b_signal"],
                      "shared": g["shared_presentation"]})
    pairs_js = json.dumps(pairs)

    js = r'''export const meta = {
  name: 'geophyto-lay-augment',
  description: 'Add lay-language layer (farmer report + plain decisive signs) to confirmed look-alike graphs',
  phases: [ { title: 'Lay' } ],
}

const PAIRS = __PAIRS__

const SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['pair_id','farmer_lay_report','decisive_lay_a','decisive_lay_b','decisive_micro_a','decisive_micro_b'],
  properties: {
    pair_id: { type: 'string', description: 'echo exactly' },
    farmer_lay_report: { type: 'string', description: '1-2 sentences a grower would say about the visible problem; NO jargon; do NOT name either decisive sign' },
    decisive_lay_a: { type: 'string', description: "member_a's decisive sign in plain grower words" },
    decisive_lay_b: { type: 'string', description: "member_b's decisive sign in plain grower words" },
    decisive_micro_a: { type: 'boolean', description: 'true if A\'s decisive sign is microscopic / needs a hand lens or lab' },
    decisive_micro_b: { type: 'boolean' },
  },
}

function prompt(p) {
  return `You are a US extension plant pathologist writing LAY-LANGUAGE text a real farmer/grower would use. `
    + `Avoid all scientific terms: never say acervuli, pycnidia, sporulation, conidia, chlorosis, lesion, `
    + `mycelium, sori, uredinia. Say things like "pinkish ooze", "fuzzy growth", "yellowing", "raised bumps", `
    + `"powdery coating", "spots".\n\n`
    + `CROP: ${p.crop}\nMEMBER_A: ${p.a}  (decisive sign, technical: ${p.sign_a})\n`
    + `MEMBER_B: ${p.b}  (decisive sign, technical: ${p.sign_b})\nSHARED LOOK: ${p.shared}\n\n`
    + `Produce:\n`
    + `- farmer_lay_report: what the grower would say about what they SEE (the shared, ambiguous problem), `
    + `WITHOUT mentioning either decisive sign, so it could be either disease.\n`
    + `- decisive_lay_a / decisive_lay_b: each member's decisive sign translated to plain grower language `
    + `(what they would look for).\n`
    + `- decisive_micro_a / decisive_micro_b: true if that sign is microscopic or needs a hand lens / lab `
    + `(not visible to the naked eye in a normal field photo).\n`
    + `Set pair_id to exactly "${p.pair_id}". Return only the JSON object.`
}

const out = await parallel(PAIRS.map((p) => () =>
  agent(prompt(p), { label: `lay:${p.pair_id}`, phase: 'Lay', schema: SCHEMA }).catch(() => null)))
const results = out.filter(Boolean)
log(`lay-augmented ${results.length}/${PAIRS.length} graphs`)
return { n: results.length, results }
'''
    js = js.replace("__PAIRS__", pairs_js)
    open(args.out, "w").write(js)
    print(f"wrote {args.out} with {len(pairs)} confirmed pairs")


if __name__ == "__main__":
    main()
