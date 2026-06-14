#!/bin/bash
#SBATCH --job-name=gpqa-s05-verify
#SBATCH --partition=nova
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:15:00
#SBATCH --output=geophyto_qa/logs/s05_%j.out
# S05 [CPU] apply gate + router: confirmed = web; clip_lane_hint = CLIP (no veto).
set -euo pipefail
cd /work/mech-ai-scratch/tirtho/GeoPlantPath
source /work/mech-ai-scratch/tirtho/.venv/bin/activate
python -m geophyto_qa.lookalike.verify_pairs \
    --web  geophyto_qa/lookalike/web_evidence.json \
    --clip geophyto_qa/lookalike/clip_scores.json \
    --out  geophyto_qa/lookalike/confirmed_lookalikes.json
