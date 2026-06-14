#!/bin/bash
#SBATCH --job-name=gpqa-s15-rebuild
#SBATCH --partition=nova
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=geophyto_qa/logs/s15_%j.out
# S15 [CPU] rebuild with corrections. Applies the S13/S14/S16 code fixes (swap,
# text-leakage, image-level splits) AND the S12 prior-audit corrections (drops
# non_discriminative/flip Lane-B items, flags undetermined). Self-check must PASS.
set -euo pipefail
cd /work/mech-ai-scratch/tirtho/GeoPlantPath
source /work/mech-ai-scratch/tirtho/.venv/bin/activate
python -m geophyto_qa.build \
    --csv BugWood_Diseases_enriched.csv --min-imgs 12 \
    --seed 20260613 --report --out geophyto_qa.jsonl \
    --corrections geophyto_qa/audit/lane_b_corrections.json
