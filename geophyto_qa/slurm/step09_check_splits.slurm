#!/bin/bash
#SBATCH --job-name=gpqa-s09-splits
#SBATCH --output=geophyto_qa/logs/step09_check_splits_%j.out
#SBATCH --error=geophyto_qa/logs/step09_check_splits_%j.err
#SBATCH --partition=nova
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:10:00
# S16 [CPU] split-hygiene gate: fails (non-zero) if any image spans >1 split.
set -euo pipefail
cd /work/mech-ai-scratch/tirtho/GeoPlantPath
source /work/mech-ai-scratch/tirtho/.venv/bin/activate
python -m geophyto_qa.audit.check_splits --jsonl geophyto_qa.jsonl
