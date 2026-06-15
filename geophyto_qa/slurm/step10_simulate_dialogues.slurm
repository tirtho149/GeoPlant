#!/bin/bash
#SBATCH --job-name=gpqa-s10-farmersim
#SBATCH --output=geophyto_qa/logs/step10_simulate_dialogues_%j.out
#SBATCH --error=geophyto_qa/logs/step10_simulate_dialogues_%j.err
#SBATCH --partition=scavenger
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=06:00:00
# S10 [GPU] PatientSim-style dynamic dialogue: replace the fixed template with a
# persona-driven farmer (vLLM) + grounded expert. Standalone transform:
#   geophyto_qa.jsonl  ->  geophyto_qa_sim.jsonl
# The expert stays graph-grounded so gold answers are unchanged.
set -euo pipefail
cd /work/mech-ai-scratch/tirtho/GeoPlantPath
source /work/mech-ai-scratch/tirtho/.venv/bin/activate
export FARMER_MODEL="${FARMER_MODEL:-Qwen/Qwen2.5-7B-Instruct}"
python -m geophyto_qa.farmer_sim \
    --backend vllm --model "$FARMER_MODEL" \
    --in geophyto_qa.jsonl --out geophyto_qa_sim.jsonl \
    --temperature 0.8 --max-tokens 80 --seed 20260613
