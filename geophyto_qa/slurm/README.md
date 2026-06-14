# SLURM runbook — look-alike diagnosis pipeline

One `.slurm` per step (full dataset). Submit from the repo root:
`sbatch geophyto_qa/slurm/stepNN_*.slurm`. Every job writes both stdout and stderr
to `geophyto_qa/logs/` as `<stepname>_%j.out` and `<stepname>_%j.err` (`%j` = job id).
Full design + I/O contracts: `../../GEOPHYTO_QA_README.md`.

| step | file | node | what |
|------|------|------|------|
| 1 | `step01_mine_pairs.slurm` | CPU | mine candidate look-alike pairs |
| 2 | `step02_identify_pairs.slurm` | CPU | pair manifest + web work-list |
| 3 | `step03_web_confirm_gen.slurm` | CPU→**Workflow** | generate web-confirm workflow ⚙ |
| 4 | `step04_clip_sweep.slurm` | **GPU** | CLIP confusability |
| 5 | `step05_verify_pairs.slurm` | CPU | confirm pairs (web gate) |
| 6 | `step06_graph_gen.slurm` | CPU→**Workflow** | generate graph/lay workflow ⚙ |
| 7 | `step07_vlm_label.slurm` | **GPU** | per-image sign-visibility labels |
| 8 | `step08_build.slurm` | CPU | build dataset |
| 9 | `step09_check_splits.slurm` | CPU | split-hygiene gate |
| — | `run_smoke10.slurm` | CPU | one-batch 10-sample smoke (build + check) |

⚙ **Steps 3 and 6** only *generate* a Workflow script in this batch. The per-pair
LLM work runs in the Claude Code Workflow engine (not sbatch):
`Workflow({scriptPath:"…/sweep_workflow_full.js"})` then `persist_sweep`; likewise
`lay_workflow_full.js` then `persist_lay`.

## Run order

Full build: 1 → 2 → (3 ⟶ Workflow ⟶ persist) → 4 → 5 → (6 ⟶ Workflow ⟶ persist)
→ 7 → 8 → 9. Steps 3/4 and 5 can overlap; 7 needs the images; 8 needs 4+5+6+7.

Adjust `--partition` (`nova` CPU / `scavenger` GPU), `--time`, `--mem` per cluster.
