#!/bin/bash
#SBATCH --job-name=gpqa-s08-build
#SBATCH --output=geophyto_qa/logs/step08_build_%j.out
#SBATCH --error=geophyto_qa/logs/step08_build_%j.err
#SBATCH --partition=scavenger
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=06:00:00
# S08 [GPU] BUILD the dataset = PatientSim-style dynamic dialogue.
# Farmer = persona vLLM agent; expert = graph-grounded (gold unchanged).
# Self-checks every item (must print PASS). The fixed-template baseline is
# `python -m geophyto_qa.build` (CPU) if ever needed for an ablation.
set -euo pipefail
cd /work/mech-ai-scratch/tirtho/GeoPlantPath
source /work/mech-ai-scratch/tirtho/.venv/bin/activate
export FARMER_MODEL="${FARMER_MODEL:-Qwen/Qwen2.5-7B-Instruct}"
python -m geophyto_qa.farmer_sim \
    --backend vllm --model "$FARMER_MODEL" \
    --csv BugWood_Diseases_enriched.csv --min-imgs 12 \
    --seed 20260613 --temperature 0.8 --max-tokens 80 \
    --out geophyto_qa.jsonl
