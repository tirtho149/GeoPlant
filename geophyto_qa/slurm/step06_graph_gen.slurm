#!/bin/bash
#SBATCH --job-name=gpqa-s06-graphgen
#SBATCH --output=geophyto_qa/logs/step06_graph_gen_%j.out
#SBATCH --error=geophyto_qa/logs/step06_graph_gen_%j.err
#SBATCH --partition=nova
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:15:00
# S06 [LLM/web] author a decision graph per confirmed pair + the lay layer.
# This batch GENERATES the workflow script; the per-pair LLM authoring runs in the
# Claude Code Workflow engine, NOT sbatch:
#   Workflow({scriptPath:"geophyto_qa/lay_workflow_full.js"})
# then persist with: python -m geophyto_qa.persist_lay --workflow-dir <transcript dir>
set -euo pipefail
cd /work/mech-ai-scratch/tirtho/GeoPlantPath
source /work/mech-ai-scratch/tirtho/.venv/bin/activate
python -m geophyto_qa.gen_lay_workflow --out geophyto_qa/lay_workflow_full.js
echo "Generated lay_workflow_full.js — execute it via the Workflow tool, then persist_lay."
