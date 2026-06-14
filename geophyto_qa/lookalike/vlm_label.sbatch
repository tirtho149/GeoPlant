#!/bin/bash
#SBATCH --job-name=gpqa-vlm
#SBATCH --partition=scavenger
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=03:00:00
#SBATCH --output=geophyto_qa/lookalike/vlm_label_%j.out
set -e
cd /work/mech-ai-scratch/tirtho/GeoPlantPath
source /work/mech-ai-scratch/tirtho/.venv/bin/activate
export VLLM_MODEL=Qwen/Qwen2.5-VL-7B-Instruct
python -m geophyto_qa.lookalike.vlm_label --cap 40
