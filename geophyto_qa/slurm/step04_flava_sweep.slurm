#!/bin/bash
#SBATCH --job-name=gpqa-s04-flava
#SBATCH --output=geophyto_qa/logs/step04_flava_sweep_%j.out
#SBATCH --error=geophyto_qa/logs/step04_flava_sweep_%j.err
#SBATCH --partition=scavenger
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=04:00:00
# S04 [GPU] THE ROUTER (natively-multimodal): FLAVA bidirectional-entailment
# confusability over ALL candidate pairs -> lane hint. Replaces CLIP cross-kNN.
# Embeddings cache to emb_cache_flava/ so re-runs are incremental.
set -euo pipefail
cd /work/mech-ai-scratch/tirtho/GeoPlantPath
source /work/mech-ai-scratch/tirtho/.venv/bin/activate
python -m geophyto_qa.lookalike.flava_confuse \
    --per-class 40 --knn-gate 0.20 \
    --out geophyto_qa/lookalike/flava_scores.json
