"""
S10 — research a cited US range statement per pathogen.   [LLM/web]

For every pathogen in the worklist, drive an LLM-with-web-tools to find its US
geographic distribution from AUTHORITATIVE sources (extension .edu / USDA / APS /
CABI) and emit one citation-based record. This is the INDEPENDENT external signal
the prior audit needs — deliberately NOT a collection count (GBIF/Bugwood share the
same sampling bias).

The driver shells out to the `claude` CLI per pathogen (matching the project's
"Claude via CLI on a compute node" pattern), expects a single JSON object back, and
merges it into the evidence store. It is RESUMABLE: pathogens already present in the
store are skipped, so it can be re-run after partial completion or failures.

Record schema (keys required), keyed by binomial in the store:
  {common, regions_present[], regions_core[], cosmopolitan, distribution,
   quote, source_url, secondary_sources[], source_type, confidence}

Usage:
  python -m geophyto_qa.audit.research_ranges \
      --worklist geophyto_qa/audit/pathogen_worklist.json \
      --out      geophyto_qa/lookalike/web_range_evidence.json
  # inspect work without calling the LLM:
  python -m geophyto_qa.audit.research_ranges --dry-run
"""
import argparse, json, os, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REGIONS = ["Northeast", "South", "Midwest", "West"]
REQUIRED = {"common", "regions_present", "regions_core", "cosmopolitan",
            "distribution", "quote", "source_url", "confidence"}

PROMPT = """You are a plant-pathology range researcher. Find the US geographic \
distribution of the pathogen below from AUTHORITATIVE sources ONLY: land-grant \
extension (.edu), USDA (.gov), APS (apsnet.org / Plant Disease / Phytopathology), \
or CABI. Do NOT use blogs or retail sites. Do NOT guess.

Pathogen: {pathogen}
Appears in this dataset as (host/disease): {appears_as}

Map US states to 4 regions:
- Northeast = ME,NH,VT,MA,RI,CT,NY,NJ,PA
- South = DE,MD,DC,VA,WV,NC,SC,GA,FL,KY,TN,AL,MS,AR,LA,OK,TX
- Midwest = OH,MI,IN,IL,WI,MN,IA,MO,KS,NE,ND,SD
- West = MT,ID,WY,NV,UT,CO,AZ,NM,AK,WA,OR,CA,HI

Decide where it OCCURS (regions_present) and where it is a MAJOR/severe/endemic \
problem (regions_core). If genuinely nationwide with no regional concentration, set \
cosmopolitan=true (regions_present=all 4, regions_core may be []). If you cannot find \
authoritative US-distribution info, set confidence="low" and regions_core=[].

Reply with ONE JSON object and NOTHING else, with exactly these keys:
{{"common": "...", "regions_present": ["South", ...], "regions_core": [...], \
"cosmopolitan": true|false, "distribution": "one line", "quote": "verbatim source \
snippet", "source_url": "...", "secondary_sources": ["..."], \
"source_type": "extension|journal|gov|cabi|other", "confidence": "high|medium|low"}}
"""


def call_claude(pathogen, appears_as, model, timeout):
    prompt = PROMPT.format(pathogen=pathogen, appears_as=", ".join(appears_as) or pathogen)
    cmd = ["claude", "-p", prompt, "--output-format", "json", "--model", model]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip()[:300] or "claude CLI failed")
    raw = out.stdout.strip()
    # --output-format json wraps the reply; the model's text is in .result
    try:
        text = json.loads(raw).get("result", raw)
    except json.JSONDecodeError:
        text = raw
    s, e = text.find("{"), text.rfind("}")
    if s < 0 or e < 0:
        raise ValueError("no JSON object in model reply")
    rec = json.loads(text[s:e + 1])
    missing = REQUIRED - rec.keys()
    if missing:
        raise ValueError(f"missing keys: {missing}")
    rec["regions_present"] = [r for r in rec.get("regions_present", []) if r in REGIONS]
    rec["regions_core"] = [r for r in rec.get("regions_core", []) if r in REGIONS]
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--worklist", default=os.path.join(ROOT, "geophyto_qa", "audit", "pathogen_worklist.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "geophyto_qa", "lookalike", "web_range_evidence.json"))
    ap.add_argument("--model", default="claude-opus-4-8")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    worklist = json.load(open(a.worklist))
    store = json.load(open(a.out)) if os.path.exists(a.out) else {}
    todo = [(p, meta) for p, meta in worklist.items() if p not in store]
    print(f"worklist: {len(worklist)}  already done: {len(store)}  to research: {len(todo)}")
    if a.dry_run:
        for p, meta in todo:
            print(f"  {meta.get('items',0):4d}  {p}  ({', '.join(meta.get('appears_as', []))})")
        return

    ok = fail = 0
    for i, (pathogen, meta) in enumerate(todo, 1):
        try:
            rec = call_claude(pathogen, meta.get("appears_as", []), a.model, a.timeout)
            store[pathogen] = rec
            json.dump(store, open(a.out, "w"), indent=2)   # incremental: resumable
            ok += 1
            print(f"[{i}/{len(todo)}] OK  {pathogen}  ({rec.get('confidence')})")
        except Exception as e:
            fail += 1
            print(f"[{i}/{len(todo)}] FAIL {pathogen}: {e}")
    print(f"\ndone: {ok} ok, {fail} failed -> {a.out}")
    if fail:
        print("re-run to retry failures (already-done pathogens are skipped).")


if __name__ == "__main__":
    main()
