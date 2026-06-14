#!/bin/bash
#SBATCH --job-name=gpqa-s12-apply
#SBATCH --output=geophyto_qa/logs/step12_apply_audit_%j.out
#SBATCH --error=geophyto_qa/logs/step12_apply_audit_%j.err
#SBATCH --partition=nova
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:10:00
# S12 [CPU] verdicts -> Lane-B corrections table (keep/relabel/drop/flag).
set -euo pipefail
cd /work/mech-ai-scratch/tirtho/GeoPlantPath
source /work/mech-ai-scratch/tirtho/.venv/bin/activate
python -m geophyto_qa.audit.apply_audit \
    --audit geophyto_qa/audit/prior_audit.json \
    --out   geophyto_qa/audit/lane_b_corrections.json
