#!/bin/bash
#SBATCH --job-name=gpqa-s08-build
#SBATCH --output=geophyto_qa/logs/step08_build_%j.out
#SBATCH --error=geophyto_qa/logs/step08_build_%j.err
#SBATCH --partition=nova
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=01:00:00
# S08 [CPU] build the dataset (initial). Self-checks every item (must print PASS).
set -euo pipefail
cd /work/mech-ai-scratch/tirtho/GeoPlantPath
source /work/mech-ai-scratch/tirtho/.venv/bin/activate
python -m geophyto_qa.build \
    --csv BugWood_Diseases_enriched.csv --min-imgs 12 \
    --seed 20260613 --report --out geophyto_qa.jsonl
