#!/bin/bash
#SBATCH --job-name=gpqa-s11-score
#SBATCH --partition=nova
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:10:00
#SBATCH --output=geophyto_qa/logs/s11_%j.out
# S11 [CPU] score the prior vs cited ranges: agree/flip/non_discriminative/undetermined.
set -euo pipefail
cd /work/mech-ai-scratch/tirtho/GeoPlantPath
source /work/mech-ai-scratch/tirtho/.venv/bin/activate
python -m geophyto_qa.audit.score_prior \
    --claims geophyto_qa/audit/pair_claims.json \
    --ranges geophyto_qa/lookalike/web_range_evidence.json \
    --out    geophyto_qa/audit/prior_audit.json
