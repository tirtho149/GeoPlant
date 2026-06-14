#!/bin/bash
#SBATCH --job-name=gpqa-s01-mine
#SBATCH --partition=nova
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=geophyto_qa/logs/s01_%j.out
# S01 [CPU] mine within-crop candidate look-alike pairs (full dataset).
set -euo pipefail
cd /work/mech-ai-scratch/tirtho/GeoPlantPath
source /work/mech-ai-scratch/tirtho/.venv/bin/activate
python -m geophyto_qa.mine_pairs \
    --csv BugWood_Diseases_enriched.csv --min-imgs 12 \
    --out geophyto_qa/pairs/candidates.json
