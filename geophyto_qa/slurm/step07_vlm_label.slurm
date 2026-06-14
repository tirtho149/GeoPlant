#!/bin/bash
#SBATCH --job-name=gpqa-s07-vlm
#SBATCH --partition=scavenger
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=06:00:00
#SBATCH --output=geophyto_qa/logs/s07_%j.out
# S07 [GPU] per-image VLM lane labels for every Bugwood image (full dataset,
# no --limit). Decides per image whether the decisive sign is visible (Lane A/B).
set -euo pipefail
cd /work/mech-ai-scratch/tirtho/GeoPlantPath
source /work/mech-ai-scratch/tirtho/.venv/bin/activate
python -m geophyto_qa.lookalike.vlm_label \
    --cap 40 --out geophyto_qa/lookalike/vlm_labels.json
