#!/bin/bash
#SBATCH --job-name=gpqa-s01-mine
#SBATCH --output=geophyto_qa/logs/step01_mine_pairs_%j.out
#SBATCH --error=geophyto_qa/logs/step01_mine_pairs_%j.err
#SBATCH --partition=nova
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=02:00:00
# S01 [CPU] mine within-crop candidate look-alike pairs from the ImageFolder
# dataset (CyAg curated, ~1.1M images / 552 hosts). Scanning the tree is the cost.
set -euo pipefail
cd /work/mech-ai-scratch/tirtho/GeoPlantPath
source /work/mech-ai-scratch/tirtho/.venv/bin/activate
export GPQA_SOURCE="${GPQA_SOURCE:-/work/mech-ai-scratch/tirtho/CyAg/Curated_Dataset/Images}"
python -m geophyto_qa.mine_pairs \
    --min-imgs 12 \
    --out geophyto_qa/pairs/candidates.json
