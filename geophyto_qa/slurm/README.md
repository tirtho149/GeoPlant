# SLURM runbook — GeoPhyto-QA full-dataset pipeline

One `.slurm` per step (full dataset). Submit from the repo root:
`sbatch geophyto_qa/slurm/stepNN_*.slurm`. Every job writes both stdout and stderr
to `geophyto_qa/logs/` as `<stepname>_%j.out` and `<stepname>_%j.err` (`%j` = job id).
Full design + I/O contracts: `../../GEOPHYTO_QA_README.md`.

| step | file | node | what |
|------|------|------|------|
| S01 | `step01_mine_pairs.slurm` | CPU | mine candidate pairs |
| S02 | `step02_identify_pairs.slurm` | CPU | pair manifest + web work-list |
| S03 | `step03_web_confirm_gen.slurm` | CPU→**Workflow** | generate web-confirm workflow ⚠ |
| S04 | `step04_clip_sweep.slurm` | **GPU** | CLIP cross-kNN router |
| S05 | `step05_verify_pairs.slurm` | CPU | apply gate+router → confirmed pairs |
| S06 | `step06_graph_gen.slurm` | CPU→**Workflow** | generate graph/lay workflow ⚠ |
| S07 | `step07_vlm_label.slurm` | **GPU** | per-image lane labels |
| S08 | `step08_build.slurm` | CPU | build dataset (initial) |
| S09 | `step09_resolve_pathogens.slurm` | CPU | resolve pathogens + claims |
| S10 | `step10_research_ranges.slurm` | CPU (LLM/web) | cited US ranges (claude CLI) |
| S11 | `step11_score_prior.slurm` | CPU | score the prior |
| S12 | `step12_apply_audit.slurm` | CPU | corrections table |
| S15 | `step15_rebuild.slurm` | CPU | rebuild with corrections |
| S16 | `step16_check_splits.slurm` | CPU | split-hygiene gate |

**S13 / S14** are code fixes (swap + text-leakage), already applied in
`geo_oracle.py` / `render_two_lane.py`; they take effect at the S15 rebuild — no
separate job.

⚠ **S03 and S06** only *generate* a Workflow script in this batch. The actual
per-pair LLM work runs in the Claude Code Workflow engine (not sbatch):
`Workflow({scriptPath:"…/sweep_workflow_full.js"})` then `persist_sweep`; likewise
`lay_workflow_full.js` then `persist_lay`. The chain is not unattended across these.

## Run order

- **Full build from scratch:** S01 → S02 → (S03⟶Workflow⟶persist) → S04 → S05 →
  (S06⟶Workflow⟶persist) → S07 → S08, then the audit chain below.
- **Prior audit + corrected rebuild (automatable):** `bash geophyto_qa/slurm/submit_audit_chain.sh`
  submits S09→S10→S11→S12→S15→S16 with `afterok` dependencies.

Adjust `--partition` (`nova` CPU / `scavenger` GPU), `--time`, `--mem` to your cluster.
