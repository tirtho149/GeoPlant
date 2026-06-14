#!/bin/bash
# Submit the fully-automatable Phase D + rebuild chain with sbatch dependencies:
#   S09 resolve -> S10 ranges -> S11 score -> S12 apply -> S15 rebuild -> S16 check
# Each step runs only if the previous succeeded (afterok). Prereq: an initial build
# (geophyto_qa.jsonl) from S08 already exists, and `claude` CLI is available for S10.
set -euo pipefail
cd /work/mech-ai-scratch/tirtho/GeoPlantPath
D=geophyto_qa/slurm
j09=$(sbatch --parsable                        $D/step09_resolve_pathogens.slurm)
j10=$(sbatch --parsable --dependency=afterok:$j09 $D/step10_research_ranges.slurm)
j11=$(sbatch --parsable --dependency=afterok:$j10 $D/step11_score_prior.slurm)
j12=$(sbatch --parsable --dependency=afterok:$j11 $D/step12_apply_audit.slurm)
j15=$(sbatch --parsable --dependency=afterok:$j12 $D/step15_rebuild.slurm)
j16=$(sbatch --parsable --dependency=afterok:$j15 $D/step16_check_splits.slurm)
echo "submitted Phase-D + rebuild chain:"
echo "  S09=$j09  S10=$j10  S11=$j11  S12=$j12  S15=$j15  S16=$j16"
echo "watch: squeue -u \$USER ; logs in geophyto_qa/logs/"
