"""
geophyto_qa.lookalike
====================
Evidence-based, TWO-LEVEL look-alike confirmation. A within-crop disease pair is
admitted as a genuine look-alike only when BOTH gates pass:

  Level 1 — IMAGE (clip_confuse.py): a CLIP image encoder embeds Bugwood photos
            of each class; the pair must be visually entangled (high cross-class
            centroid similarity and/or a high kNN cross-confusion rate).

  Level 2 — LABEL (web_verify.py): a web search must return a credible source
            (extension / university / peer-reviewed) that states the two are
            confused / look alike, captured as a quoted snippet + URL.

verify_pairs.py intersects the two into confirmed_lookalikes.json, which gates
the dataset build; each confirmed pair carries its CLIP score and its web quote.
"""
