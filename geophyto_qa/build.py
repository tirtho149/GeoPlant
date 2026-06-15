"""
geophyto_qa.build
================
Orchestrate the GeoPhyto-QA build:

    load enriched CSV
      -> splits (train / test_random / test_heldout_region / test_heldout_species)
      -> for each mined pair that HAS a validated discriminator graph:
             for each image of each member where the deciding sign is visible
             -> render an image->label diagnosis item
      -> self-check  -> geophyto_qa.jsonl

Graphs come from geophyto_qa/graphs/{gold,generated}. Pairs without a graph yet
are reported as pending (no silent truncation) — generate them with the
graphgen Workflow fan-out and re-run.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from geophyto_qa.graphgen import load_gold, load_generated, GEN_DIR  # noqa: E402
from geophyto_qa.schema import validate_graph, decisive_fork  # noqa: E402
from geophyto_qa.mine_pairs import mine, pair_key        # noqa: E402
from geophyto_qa.render_item import render as render_item  # noqa: E402
from geophyto_qa.data_source import load_rows, DEFAULT_SOURCE  # noqa: E402
from geophyto_qa.quality.label_gate import filter_rows      # noqa: E402  (step-0 gate; no-op if absent)

VLM_LABELS = os.path.join(HERE, "lookalike", "vlm_labels.json")


def load_vlm_labels():
    return json.load(open(VLM_LABELS)) if os.path.exists(VLM_LABELS) else {}


# load_rows now lives in geophyto_qa.data_source (handles both an image directory
# and the legacy Bugwood CSV; imported above).


def make_splits(rows, rng, n_region_states=6, n_species_frac=0.12, random_frac=0.12):
    by_state = collections.Counter(r["state"] for r in rows)
    mids = [s for s, c in by_state.items() if 40 <= c <= 250]
    rng.shuffle(mids)
    region_states = set(mids[:n_region_states])
    crops = sorted({r["crop"] for r in rows})
    rng.shuffle(crops)
    held_species = set(crops[:max(1, int(len(crops) * n_species_frac))])
    split = {}
    for i, r in enumerate(rows):
        if r["state"] in region_states:
            split[i] = "test_heldout_region"
        elif r["crop"] in held_species:
            split[i] = "test_heldout_species"
        elif rng.random() < random_frac:
            split[i] = "test_random"
        else:
            split[i] = "train"
    # S16 split hygiene: an image_number can appear in several rows; collapse to
    # image level (first occurrence wins) so no image ever spans two splits.
    img_split = {}
    for i, r in enumerate(rows):
        im = r.get("img")
        if not im:
            continue
        if im in img_split:
            split[i] = img_split[im]
        else:
            img_split[im] = split[i]
    return split


def graphs_by_pair():
    """pair_id -> record, from gold + generated (generated wins on conflict)."""
    out = {}
    for rec in load_gold():
        out[rec["pair_id"]] = rec
    out.update(load_generated())
    return out


def load_confirmed():
    """pair_id -> two-level look-alike evidence (CLIP + web). Empty if absent."""
    path = os.path.join(HERE, "lookalike", "confirmed_lookalikes.json")
    return json.load(open(path)) if os.path.exists(path) else {}


# --------------------------------------------------------------------------- #
def select_items(source, min_imgs, seed, require_evidence=True):
    """Pick which (pair x member x image) become items, with split + evidence +
    technical sign. Shared by the template build() and the dynamic farmer_sim, so
    both produce the SAME item set (only the dialogue differs). Filtering by image
    quality (close-up / sign-visible) happens later in item_skeleton.
    Returns (selected, coverage)."""
    rows, gate = filter_rows(load_rows(source))
    rng = random.Random(seed)
    split = make_splits(rows, rng)

    pairs = mine(rows, min_imgs)
    graphs = graphs_by_pair()
    confirmed = load_confirmed()
    vlm_labels = load_vlm_labels()

    # index images by (crop, disease)
    by_cd = collections.defaultdict(list)
    idx_of = {}
    for i, r in enumerate(rows):
        by_cd[(r["crop"], r["disease"])].append(r)
        idx_of[id(r)] = i

    selected = []
    used_pairs = 0
    pending = []
    dropped_nonconfusable = []
    unconfirmed = []        # has a graph but failed the two-level look-alike gate
    for p in pairs:
        rec = graphs.get(p["pair_id"])
        if rec is None:
            pending.append(p["pair_id"])
            continue
        g = rec["graph"]
        if validate_graph(g):
            pending.append(p["pair_id"] + " (invalid graph)")
            continue
        if not g.get("confusable", False):
            dropped_nonconfusable.append(p["pair_id"])
            continue
        # WEB-GATE look-alike confirmation (FLAVA bidir no longer vetoes; it routes).
        ev = confirmed.get(p["pair_id"])
        if require_evidence and not (ev and ev.get("confirmed")):
            why = "no evidence" if not ev else "web✗"
            unconfirmed.append(f"{p['pair_id']} ({why})")
            continue
        evidence = {
            "web_verified": (ev or {}).get("web_verified"),
            "clip_lane_hint": (ev or {}).get("clip_lane_hint"),
            "image_confusable": (ev or {}).get("image_confusable"),  # descriptor
            "clip": (ev or {}).get("clip", {}),
            "web_quote": (ev or {}).get("web", {}).get("quote"),
            "web_source_url": (ev or {}).get("web", {}).get("source_url"),
            "web_source_title": (ev or {}).get("web", {}).get("source_title"),
        } if ev else None
        used_pairs += 1
        ma, mb = p["member_a"]["disease"], p["member_b"]["disease"]
        tech = {"a": decisive_fork(g)["a_signal"], "b": decisive_fork(g)["b_signal"]}
        for member, dis in (("a", ma), ("b", mb)):
            for r in by_cd[(p["crop"], dis)]:
                selected.append({
                    "rec": rec, "g": g, "r": r, "member": member,
                    "split": split[idx_of[id(r)]], "vlm": vlm_labels.get(r["img"]),
                    "evidence": evidence, "tech": tech[member],
                })
    coverage = {"pairs": pairs, "used_pairs": used_pairs, "pending": pending,
                "dropped_nonconfusable": dropped_nonconfusable, "unconfirmed": unconfirmed,
                "label_gate": gate}
    return selected, coverage


def build(source, min_imgs, seed, out_path, report=False, max_items=None,
          require_evidence=True):
    selected, cov = select_items(source, min_imgs, seed, require_evidence)
    pairs, used_pairs = cov["pairs"], cov["used_pairs"]
    pending = cov["pending"]
    dropped_nonconfusable, unconfirmed = cov["dropped_nonconfusable"], cov["unconfirmed"]

    items = []
    for c in selected:
        it = render_item(c["rec"], c["g"], c["r"], c["member"], c["split"], c["vlm"], seed)
        if it is None:                       # dropped (no close-up / deciding sign not visible)
            continue
        it["lookalike"]["evidence"] = c["evidence"]
        it["_tech_decisive"] = c["tech"]     # for anti-leakage check; stripped before write
        items.append(it)
        if max_items and len(items) >= max_items:
            break

    fails = selfcheck(items)
    for it in items:
        it.pop("_tech_decisive", None)               # don't ship the technical sign
    status = "PASS" if not fails else "FAIL"

    with open(out_path, "w") as fh:
        for it in items:
            fh.write(json.dumps(it) + "\n")

    summary = {
        "n_items": len(items),
        "pairs_with_graph": used_pairs,
        "pairs_total_candidates": len(pairs),
        "pairs_pending_graph": len(pending),
        "pairs_dropped_nonconfusable": len(dropped_nonconfusable),
        "pairs_unconfirmed_lookalike": len(unconfirmed),
        "require_evidence": require_evidence,
        "splits": dict(collections.Counter(it["split"] for it in items)),
        "selfcheck": status,
        "selfcheck_fails": fails[:20],
    }
    coverage_path = out_path.replace(".jsonl", ".coverage.json")
    with open(coverage_path, "w") as fh:
        json.dump({"pending_pairs": pending,
                   "dropped_nonconfusable": dropped_nonconfusable,
                   "unconfirmed_lookalike": unconfirmed,
                   "summary": summary}, fh, indent=2)

    print(f"[{status}] wrote {len(items)} items -> {out_path}")
    print(f"  graphs: {used_pairs} confirmed-used / {len(pending)} pending-graph / "
          f"{len(unconfirmed)} graph-but-unconfirmed / "
          f"{len(dropped_nonconfusable)} non-confusable  of {len(pairs)} candidate pairs")
    print(f"  look-alike gate: require_evidence={require_evidence} "
          f"(CLIP image + web source)")
    print(f"  splits: {summary['splits']}")
    if pending:
        print(f"  NOTE: {len(pending)} pairs lack a graph -> run graphgen sweep "
              f"and re-build. Coverage detail: {coverage_path}")
    if unconfirmed:
        print(f"  NOTE: {len(unconfirmed)} graphed pairs failed the CLIP+web "
              f"look-alike gate (see coverage).")
    if report and items:
        _print_sample(items[0])
    return summary


def selfcheck(items):
    """Image->label gates. Headline = ANTI-LEAKAGE: the graph's *technical* decisive
    sign must never appear in any farmer turn; the expert reads it FROM the image."""
    fails = []
    for it in items:
        iid = it["item_id"]
        farmer = " ".join(t["text"].lower() for t in it["dialogue"] if t["speaker"] == "farmer")
        # 1) ANTI-LEAKAGE: technical decisive sign not handed over by the farmer.
        tech = (it.get("_tech_decisive") or "").lower().strip().rstrip(".")
        if tech and tech in farmer:
            fails.append((iid, "LEAK: technical decisive sign in farmer turn"))
        # 2) CoT ends in CONCLUDE; reads the sign from the image; diagnosis != distractor.
        if not it["cot"] or it["cot"][-1]["step"] != "CONCLUDE":
            fails.append((iid, "no CONCLUDE"))
        if "READ_SIGN" not in [s["step"] for s in it["cot"]]:
            fails.append((iid, "no READ_SIGN step"))
        if it["gold"]["diagnosis"] == it["lookalike"]["distractor"]:
            fails.append((iid, "diagnosis == distractor"))
        if not it["gold"].get("answerable_from_image"):
            fails.append((iid, "not answerable-from-image"))
        # 3) first farmer turn carries the image.
        if not it["dialogue"][0].get("has_image"):
            fails.append((iid, "F1 has no image"))
        # 4) look-alike evidence present (WEB GATE — CLIP is a router, not required).
        ev = it["lookalike"].get("evidence")
        if ev is not None and not (ev.get("web_verified") and ev.get("web_source_url")):
            fails.append((iid, "look-alike evidence incomplete (web source missing)"))
    return fails


def _print_sample(it):
    print("\n--- SAMPLE ITEM ---")
    print(f"{it['item_id']}  [{it['split']}]  "
          f"{it['lookalike']['true']} vs {it['lookalike']['distractor']}  "
          f"host={it['grounding']['host']} part={it['grounding']['anatomical_part']}")
    for t in it["dialogue"]:
        tag = "(img)" if t["has_image"] else "     "
        print(f"  [{t['turn']}]{tag} {t['speaker']:6s}: {t['text']}")
    print("  CoT:")
    for s in it["cot"]:
        print(f"    {s['step']:14s} {s['text']}")
    print(f"  gold: dx={it['gold']['diagnosis']}  ruled_out={it['gold']['ruled_out']} "
          f"| evidence_from_image={it['gold']['evidence_from_image'][:70]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=DEFAULT_SOURCE,
                    help="ImageFolder dataset dir (default: GPQA_SOURCE / CyAg)")
    ap.add_argument("--min-imgs", type=int, default=12)
    ap.add_argument("--seed", type=int, default=20260613)
    ap.add_argument("--out", default=os.path.join(ROOT, "geophyto_qa.jsonl"))
    ap.add_argument("--max", type=int, default=None, help="cap items (smoke test)")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--no-require-evidence", action="store_true",
                    help="skip the web look-alike gate (debug only)")
    args = ap.parse_args()
    build(args.source, args.min_imgs, args.seed, args.out, args.report, args.max,
          require_evidence=not args.no_require_evidence)


if __name__ == "__main__":
    main()
