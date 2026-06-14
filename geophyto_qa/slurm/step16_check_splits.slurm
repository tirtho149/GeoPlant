#!/bin/bash
#SBATCH --job-name=gpqa-s16-splits
#SBATCH --partition=nova
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:10:00
#SBATCH --output=geophyto_qa/logs/s16_%j.out
# S16 [CPU] split-hygiene gate: fails (non-zero) if any image spans >1 split.
set -euo pipefail
cd /work/mech-ai-scratch/tirtho/GeoPlantPath
source /work/mech-ai-scratch/tirtho/.venv/bin/activate
python -m geophyto_qa.audit.check_splits --jsonl geophyto_qa.jsonl
