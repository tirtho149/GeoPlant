"""
geophyto_qa.audit — prior validation (Phase D) + integrity checks.

The contributor-count regional prior is the load-bearing assumption behind Lane-B
gold. This package validates it against an INDEPENDENT, citation-based external
range signal (authoritative extension/USDA/APS range *statements* — never another
collection count such as GBIF, which shares Bugwood's sampling bias).

Pipeline (see GEOPHYTO_QA_README.md, Phase D/F):
    S09 resolve_pathogens  -> pathogen_worklist.json, pair_claims.json
    S10 research_ranges    -> ../lookalike/web_range_evidence.json   (LLM/web)
    S11 score_prior        -> prior_audit.json
    S12 apply_audit        -> lane_b_corrections.json
    S16 check_splits       -> split-leakage assertion
"""
