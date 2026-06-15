#!/bin/bash
#SBATCH --job-name=gpqa-sweep-soybean
#SBATCH --output=geophyto_qa/logs/sweep_soybean_%j.out
#SBATCH --error=geophyto_qa/logs/sweep_soybean_%j.err
#SBATCH --partition=scavenger
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=12:00:00
# ============================================================================
# FULL SWEEP for ONE crop (SOYBEAN), end to end, in a single GPU job.
#   GPQA_CROP=Soybean restricts the ImageFolder dataset to the Soybean host only.
#   LLM/web steps (0 label-judge, 3 web-confirm, 6 graphgen) run via the `claude`
#   CLI; GPU steps (4 FLAVA, 7 VLM, 8 build) run on this node. Each step writes its
#   own artifact, so the run is resumable (re-submitting skips finished work).
# Output: geophyto_qa_soybean.jsonl
# ============================================================================
set -euo pipefail
cd /work/mech-ai-scratch/tirtho/GeoPlantPath
source /work/mech-ai-scratch/tirtho/.venv/bin/activate

export GPQA_SOURCE="${GPQA_SOURCE:-/work/mech-ai-scratch/tirtho/CyAg/Curated_Dataset/Images}"
export GPQA_CROP="Soybean"                       # <-- the only knob: restrict to soybean
export GPQA_JUDGE_MODEL="${GPQA_JUDGE_MODEL:-claude-opus-4-8}"
export GPQA_WEB_MODEL="${GPQA_WEB_MODEL:-claude-opus-4-8}"
export GPQA_GRAPH_MODEL="${GPQA_GRAPH_MODEL:-claude-opus-4-8}"
export FARMER_MODEL="${FARMER_MODEL:-Qwen/Qwen2.5-7B-Instruct}"
export VLLM_MODEL="${VLLM_MODEL:-Qwen/Qwen2.5-VL-7B-Instruct}"
OUT=geophyto_qa_soybean.jsonl

echo "##### STEP 0  label QA (claude) #####"
python -m geophyto_qa.quality.disease_label_judge --min-imgs 12

echo "##### STEP 1  mine pairs #####"
python -m geophyto_qa.mine_pairs --min-imgs 12 --out geophyto_qa/pairs/candidates.json

echo "##### STEP 2  identify pairs (manifest + worklist) #####"
python -m geophyto_qa.lookalike.identify_pairs --min-imgs 12 --out-dir geophyto_qa/pairs

echo "##### STEP 3  web-confirm (GATE, claude) #####"
python -m geophyto_qa.lookalike.web_confirm_cli --pairs geophyto_qa/pairs/candidates.json

echo "##### STEP 4  FLAVA bidirectional-entailment confusability (GPU) #####"
python -m geophyto_qa.lookalike.flava_confuse --per-class 40 --knn-gate 0.20 \
    --out geophyto_qa/lookalike/flava_scores.json

echo "##### STEP 5  verify pairs (confirmed = web; FLAVA attached) #####"
python -m geophyto_qa.lookalike.verify_pairs \
    --clip geophyto_qa/lookalike/flava_scores.json \
    --web  geophyto_qa/lookalike/web_evidence.json \
    --out  geophyto_qa/lookalike/confirmed_lookalikes.json

echo "##### STEP 6  graph generation (claude) #####"
python -m geophyto_qa.graph_gen_cli --pairs geophyto_qa/pairs/candidates.json

echo "##### STEP 7  VLM sign-visibility labels (GPU) #####"
python -m geophyto_qa.lookalike.vlm_label --cap 40

echo "##### STEP 8  BUILD = dynamic persona dialogue (GPU) #####"
python -m geophyto_qa.farmer_sim --backend vllm --model "$FARMER_MODEL" \
    --min-imgs 12 --seed 20260613 --temperature 0.8 --max-tokens 80 --out "$OUT"

echo "##### STEP 9  split-hygiene check #####"
python -m geophyto_qa.audit.check_splits --jsonl "$OUT"

echo "##### SOYBEAN SWEEP DONE -> $OUT #####"
