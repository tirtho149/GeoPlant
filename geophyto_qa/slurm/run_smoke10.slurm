#!/bin/bash
#SBATCH --job-name=gpqa-smoke10
#SBATCH --output=geophyto_qa/logs/run_smoke10_%j.out
#SBATCH --error=geophyto_qa/logs/run_smoke10_%j.err
#SBATCH --partition=nova
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:20:00
# ----------------------------------------------------------------------------
# 10-sample smoke run of the WHOLE deterministic pipeline in ONE batch.
# Builds 10 items from the existing upstream artifacts (confirmed pairs + graphs +
# VLM labels), then runs the prior-audit + split-hygiene check on them. No GPU and
# no Workflow/LLM steps needed. Writes to *_smoke10.* so the real dataset is untouched.
# ----------------------------------------------------------------------------
set -euo pipefail
cd /work/mech-ai-scratch/tirtho/GeoPlantPath
source /work/mech-ai-scratch/tirtho/.venv/bin/activate

OUT=geophyto_qa_smoke10.jsonl
A=geophyto_qa/audit

echo "==== [1/4] build 10 sample items ===="
python -m geophyto_qa.build \
    --csv BugWood_Diseases_enriched.csv --min-imgs 12 --seed 20260613 \
    --max 10 --report --out "$OUT"

echo "==== [2/4] resolve pathogens + pair-claims (on the 10 samples) ===="
python -m geophyto_qa.audit.resolve_pathogens \
    --jsonl "$OUT" --csv BugWood_Diseases_enriched.csv \
    --out-pathogens "$A/smoke_pathogen_worklist.json" \
    --out-claims    "$A/smoke_pair_claims.json"

echo "==== [3/4] score the prior vs cited ranges ===="
python -m geophyto_qa.audit.score_prior \
    --claims "$A/smoke_pair_claims.json" \
    --ranges geophyto_qa/lookalike/web_range_evidence.json \
    --out    "$A/smoke_prior_audit.json"

echo "==== [4/4] split-hygiene check ===="
python -m geophyto_qa.audit.check_splits --jsonl "$OUT"

echo; echo "==== sample item ===="
head -1 "$OUT" | python -m json.tool | head -45
echo; echo "DONE -> $OUT (+ $A/smoke_*.json)"
