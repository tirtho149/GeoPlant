"""
geophyto_qa
===========
GeoPhyto-QA: long-context, image-grounded farmer<->ag-expert VQA where the
expert reasons through a **look-alike decision graph** (the docx CoT flow) and
the reasoning is **geography-aware** (region / season / local disease pressure
drive the answer).

Pipeline (see GEOPHYTO_QA_README.md):

    mine_pairs   -> candidate within-crop look-alike disease pairs (work-list)
    graphgen     -> LLM-authored discriminator decision graph per pair (validated)
    geo_oracle   -> contributor-de-biased TRAIN-only prior + localizability gate
    render_dialogue -> deterministic farmer<->expert dialogue + gold + swap
    build        -> orchestrate + self-check -> geophyto_qa.jsonl

Constraints: Bugwood-only, USA-only, contributor-de-biased geographic oracle.
"""
