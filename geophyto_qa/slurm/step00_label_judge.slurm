#!/bin/bash
#SBATCH --job-name=gpqa-s00-labeljudge
#SBATCH --output=geophyto_qa/logs/step00_label_judge_%j.out
#SBATCH --error=geophyto_qa/logs/step00_label_judge_%j.err
#SBATCH --partition=nova
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=24:00:00
# S00 [CPU + claude CLI] LLM-as-judge dataset LABEL quality check (ported from
# tirtho149/SAGE). Layer 1 validates crop names, Layer 2 judges disease labels.
# Writes geophyto_qa/quality/disease_label_full_report.json, which step 1 (mining)
# and the build then honor via quality.label_gate (drop INVALID/NON_CROP crops +
# INCORRECT diseases, rename misspelled crops). Resumable.
set -euo pipefail
cd /work/mech-ai-scratch/tirtho/GeoPlantPath
source /work/mech-ai-scratch/tirtho/.venv/bin/activate
export GPQA_SOURCE="${GPQA_SOURCE:-/work/mech-ai-scratch/tirtho/CyAg/Curated_Dataset/Images}"
export GPQA_JUDGE_MODEL="${GPQA_JUDGE_MODEL:-claude-opus-4-8}"
python -m geophyto_qa.quality.disease_label_judge --min-imgs 12
