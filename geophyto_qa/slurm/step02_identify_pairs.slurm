#!/bin/bash
#SBATCH --job-name=gpqa-s02-identify
#SBATCH --partition=nova
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=geophyto_qa/logs/s02_%j.out
# S02 [CPU] reproducible pair manifest + web work-list (full dataset).
set -euo pipefail
cd /work/mech-ai-scratch/tirtho/GeoPlantPath
source /work/mech-ai-scratch/tirtho/.venv/bin/activate
python -m geophyto_qa.lookalike.identify_pairs \
    --csv BugWood_Diseases_enriched.csv --min-imgs 12 \
    --out-dir geophyto_qa/pairs
