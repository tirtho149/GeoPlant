#!/bin/bash
#SBATCH --job-name=gpqa-s04-clip
#SBATCH --partition=scavenger
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH --output=geophyto_qa/logs/s04_%j.out
# S04 [GPU] THE ROUTER: CLIP cross-kNN over ALL candidate pairs -> lane hint.
# Embeddings cache to emb_cache/ so re-runs are incremental.
set -euo pipefail
cd /work/mech-ai-scratch/tirtho/GeoPlantPath
source /work/mech-ai-scratch/tirtho/.venv/bin/activate
python -m geophyto_qa.lookalike.clip_confuse \
    --per-class 40 --knn-thresh 0.12 \
    --out geophyto_qa/lookalike/clip_scores.json
