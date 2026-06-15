#!/bin/bash
#SBATCH --job-name=gpqa-smoke10
#SBATCH --output=geophyto_qa/logs/run_smoke10_%j.out
#SBATCH --error=geophyto_qa/logs/run_smoke10_%j.err
#SBATCH --partition=nova
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:20:00
# ----------------------------------------------------------------------------
# 10-sample smoke run of the image->label pipeline in ONE batch. Builds 10 items
# from the existing upstream artifacts (confirmed pairs + graphs + VLM labels) and
# runs the split-hygiene check. No GPU / no Workflow. Writes to *_smoke10.* so the
# real dataset is untouched.
# ----------------------------------------------------------------------------
set -euo pipefail
cd /work/mech-ai-scratch/tirtho/GeoPlantPath
source /work/mech-ai-scratch/tirtho/.venv/bin/activate
export GPQA_SOURCE="${GPQA_SOURCE:-/work/mech-ai-scratch/tirtho/CyAg/Curated_Dataset/Images}"

OUT=geophyto_qa_smoke10.jsonl
echo "==== build 10 image->label items (template baseline; needs upstream graphs+confirmed+VLM for this source) ===="
python -m geophyto_qa.build \
    --min-imgs 12 --seed 20260613 \
    --max 10 --report --out "$OUT"

echo "==== split-hygiene check ===="
python -m geophyto_qa.audit.check_splits --jsonl "$OUT"
echo "DONE -> $OUT"
