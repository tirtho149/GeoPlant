#!/bin/bash
#SBATCH --job-name=gpqa-s09-resolve
#SBATCH --partition=nova
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=00:15:00
#SBATCH --output=geophyto_qa/logs/s09_%j.out
# S09 [CPU] resolve Lane-B (host,disease) -> pathogen binomial; emit worklist + claims.
set -euo pipefail
cd /work/mech-ai-scratch/tirtho/GeoPlantPath
source /work/mech-ai-scratch/tirtho/.venv/bin/activate
python -m geophyto_qa.audit.resolve_pathogens \
    --jsonl geophyto_qa.jsonl --csv BugWood_Diseases_enriched.csv \
    --out-pathogens geophyto_qa/audit/pathogen_worklist.json \
    --out-claims    geophyto_qa/audit/pair_claims.json
