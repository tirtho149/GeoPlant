#!/bin/bash
#SBATCH --job-name=gpqa-s03-webgen
#SBATCH --output=geophyto_qa/logs/step03_web_confirm_gen_%j.out
#SBATCH --error=geophyto_qa/logs/step03_web_confirm_gen_%j.err
#SBATCH --partition=nova
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:15:00
# S03 [LLM/web] THE GATE: web-confirm look-alikes.
# This batch only GENERATES the workflow script over ALL candidates. The actual
# web verification (quote+URL per pair) is executed by the Claude Code Workflow
# engine, NOT by sbatch:  Workflow({scriptPath:"geophyto_qa/lookalike/sweep_workflow_full.js"})
# then persist with:  python -m geophyto_qa.lookalike.persist_sweep --workflow-dir <transcript dir>
set -euo pipefail
cd /work/mech-ai-scratch/tirtho/GeoPlantPath
source /work/mech-ai-scratch/tirtho/.venv/bin/activate
python -m geophyto_qa.lookalike.gen_sweep_workflow \
    --pairs geophyto_qa/pairs/candidates.json --top 100000 \
    --out geophyto_qa/lookalike/sweep_workflow_full.js
echo "Generated sweep_workflow_full.js — execute it via the Workflow tool, then persist_sweep."
