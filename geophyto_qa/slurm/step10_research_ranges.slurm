#!/bin/bash
#SBATCH --job-name=gpqa-s10-ranges
#SBATCH --output=geophyto_qa/logs/step10_research_ranges_%j.out
#SBATCH --error=geophyto_qa/logs/step10_research_ranges_%j.err
#SBATCH --partition=nova
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=08:00:00
# S10 [LLM/web] cited US range per pathogen -> web_range_evidence.json.
# Drives the `claude` CLI once per pathogen (resumable: re-run to retry failures;
# already-done pathogens are skipped). Requires `claude` on PATH with web access.
set -euo pipefail
cd /work/mech-ai-scratch/tirtho/GeoPlantPath
source /work/mech-ai-scratch/tirtho/.venv/bin/activate
python -m geophyto_qa.audit.research_ranges \
    --worklist geophyto_qa/audit/pathogen_worklist.json \
    --out      geophyto_qa/lookalike/web_range_evidence.json
