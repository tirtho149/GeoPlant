"""
geophyto_qa.lookalike.vlm_label
==============================
Vision pass over the confirmed look-alike pairs' images with Qwen2.5-VL (vLLM).
Per image it produces:

  * anatomical_part      -> feeds the SAGE-style Organ Part Index
  * is_closeup           -> drop wide field/landscape shots
  * decisive_sign_visible-> Lane A (visible -> image-decisive) vs Lane B (not)
  * lay_observation      -> plain grower language for the farmer turn (no jargon)

This is what makes the redesign honest: the decisive sign is only used as an
image-decisive cue when the VLM confirms it is actually visible in THAT photo,
and the farmer speaks from lay_observation, never the technical sign.

Output: geophyto_qa/lookalike/vlm_labels.json  {image_number: {...}}

Run on a GPU node:  sbatch geophyto_qa/lookalike/vlm_label.sbatch
Smoke (few images):  python -m geophyto_qa.lookalike.vlm_label --limit 8
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys
from io import BytesIO

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
ROOT = os.path.dirname(PKG)
sys.path.insert(0, ROOT)
from geophyto_qa.lookalike.clip_confuse import _fetch                 # noqa: E402
from geophyto_qa.build import graphs_by_pair, load_confirmed          # noqa: E402
from geophyto_qa.schema import decisive_fork                          # noqa: E402

CSV = os.path.join(ROOT, "BugWood_Diseases_enriched.csv")
OUT = os.path.join(HERE, "vlm_labels.json")
MODEL = os.environ.get("VLLM_MODEL", "Qwen/Qwen2.5-VL-7B-Instruct")

PART_ENUM = ["leaf", "stem", "root", "fruit", "flower", "pod", "seed", "whole_plant"]
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["anatomical_part", "is_closeup", "decisive_sign_visible", "lay_observation"],
    "properties": {
        "anatomical_part": {"type": "string", "enum": PART_ENUM},
        "is_closeup": {"type": "boolean"},
        "decisive_sign_visible": {"type": "boolean"},
        "lay_observation": {"type": "string"},
    },
}


def member_signs():
    """(crop, disease) -> decisive sign text (for the member as the TRUE class)."""
    out = {}
    conf = load_confirmed()
    graphs = graphs_by_pair()
    for pid, d in conf.items():
        if not d.get("confirmed"):
            continue
        rec = graphs.get(pid)
        if not rec:
            continue
        fk = decisive_fork(rec["graph"])
        if not fk:
            continue
        out[(d["crop"], d["member_a"])] = fk["a_signal"]
        out[(d["crop"], d["member_b"])] = fk["b_signal"]
    return out


def gather_images(members, cap):
    import csv as csvmod
    by = collections.defaultdict(list)
    for r in csvmod.DictReader(open(CSV, newline="")):
        k = (r["NormCrop"], r["NormDisease"])
        if k in members:
            by[k].append((r["Image Number"], r.get("Descriptor Name", "")))
    items = []
    for k, rows in by.items():
        for num, desc in sorted(set(rows))[:cap]:
            items.append({"img": num, "crop": k[0], "disease": k[1], "descriptor": desc})
    return items


def prompt_text(crop, disease, sign):
    return (
        f"This is a photograph labeled as the plant disease '{disease}' on {crop}. "
        f"Answer about THIS photo only.\n"
        f"1) anatomical_part: which plant part is the main subject "
        f"(leaf, stem, root, fruit, flower, pod, seed, or whole_plant)?\n"
        f"2) is_closeup: true if it is a close view of lesions/signs on plant tissue, "
        f"false if it is a wide field/landscape/whole-scene shot.\n"
        f"3) decisive_sign_visible: is this specific diagnostic sign CLEARLY visible in "
        f"the photo: \"{sign}\"? Answer true only if you can actually see it here.\n"
        f"4) lay_observation: one sentence in plain grower language (NO scientific terms) "
        f"describing what looks wrong with the plant in this photo."
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cap", type=int, default=40, help="images per member class")
    ap.add_argument("--limit", type=int, default=None, help="smoke: cap total images")
    ap.add_argument("--max-pixels", type=int, default=768 * 768)
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    signs = member_signs()
    members = set(signs)
    items = gather_images(members, args.cap)
    if args.limit:
        items = items[:args.limit]
    print(f"VLM labeling {len(items)} images across {len(members)} member classes", flush=True)

    from PIL import Image
    from transformers import AutoProcessor
    from vllm import LLM, SamplingParams
    from vllm.sampling_params import StructuredOutputsParams

    # download + decode (concurrent)
    from concurrent.futures import ThreadPoolExecutor
    def fetch(it):
        raw = _fetch(it["img"], timeout=15)
        if not raw:
            return None
        try:
            img = Image.open(BytesIO(raw)).convert("RGB")
        except Exception:
            return None
        img.thumbnail((int(args.max_pixels ** 0.5), int(args.max_pixels ** 0.5)))
        it["_img"] = img
        return it
    with ThreadPoolExecutor(max_workers=16) as ex:
        items = [x for x in ex.map(fetch, items) if x]
    print(f"fetched {len(items)} images", flush=True)

    proc = AutoProcessor.from_pretrained(MODEL)
    llm = LLM(model=MODEL, max_model_len=4096, limit_mm_per_prompt={"image": 1},
              gpu_memory_utilization=0.92, dtype="bfloat16", enforce_eager=True)
    sp = SamplingParams(temperature=0.0, max_tokens=400,
                        structured_outputs=StructuredOutputsParams(json=SCHEMA))

    prompts = []
    for it in items:
        msgs = [{"role": "user", "content": [
            {"type": "image"},
            {"type": "text", "text": prompt_text(it["crop"], it["disease"],
                                                 signs[(it["crop"], it["disease"])])}]}]
        text = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        prompts.append({"prompt": text, "multi_modal_data": {"image": it["_img"]}})

    outs = llm.generate(prompts, sp)
    labels = {}
    for it, o in zip(items, outs):
        try:
            j = json.loads(o.outputs[0].text)
        except Exception:
            continue
        labels[it["img"]] = {"crop": it["crop"], "disease": it["disease"],
                             "descriptor": it["descriptor"], **j}
    json.dump(labels, open(args.out, "w"), indent=2)
    n_cu = sum(1 for v in labels.values() if v.get("is_closeup"))
    n_vis = sum(1 for v in labels.values() if v.get("decisive_sign_visible"))
    print(f"wrote {len(labels)} labels -> {args.out}  (close-up {n_cu}, sign-visible {n_vis})",
          flush=True)
    print("part distribution:",
          dict(collections.Counter(v["anatomical_part"] for v in labels.values())))


if __name__ == "__main__":
    main()
