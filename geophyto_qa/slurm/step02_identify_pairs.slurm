#!/bin/bash
#SBATCH --job-name=gpqa-s02-identify
#SBATCH --output=geophyto_qa/logs/step02_identify_pairs_%j.out
#SBATCH --error=geophyto_qa/logs/step02_identify_pairs_%j.err
#SBATCH --partition=nova
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=02:00:00
# S02 [CPU] reproducible pair manifest + web work-list (ImageFolder dataset).
set -euo pipefail
cd /work/mech-ai-scratch/tirtho/GeoPlantPath
source /work/mech-ai-scratch/tirtho/.venv/bin/activate
export GPQA_SOURCE="${GPQA_SOURCE:-/work/mech-ai-scratch/tirtho/CyAg/Curated_Dataset/Images}"
python -m geophyto_qa.lookalike.identify_pairs \
    --min-imgs 12 \
    --out-dir geophyto_qa/pairs
