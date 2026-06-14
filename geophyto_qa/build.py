"""
geophyto_qa.build
================
Orchestrate the GeoPhyto-QA build:

    load enriched CSV
      -> splits (train / test_random / test_heldout_region / test_heldout_species)
      -> contributor-de-biased GeoOracle (TRAIN only)
      -> for each mined pair that HAS a validated discriminator graph:
             for each image of each member -> render a dialogue item
      -> self-check  -> geophyto_qa.jsonl

Graphs come from geophyto_qa/graphs/{gold,generated}. Pairs without a graph yet
are reported as pending (no silent truncation) — generate them with the
graphgen Workflow fan-out and re-run.
"""
from __future__ import annotations

import argparse
import collections
import csv as csvmod
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from utils.geo import decode_state                       # noqa: E402
from geophyto_qa.regions import CENSUS_DIVISION, region_of  # noqa: E402
from geophyto_qa.geo_oracle import GeoOracle             # noqa: E402
from geophyto_qa.graphgen import load_gold, load_generated, GEN_DIR  # noqa: E402
from geophyto_qa.schema import validate_graph, decisive_fork  # noqa: E402
from geophyto_qa.mine_pairs import mine, pair_key        # noqa: E402
from geophyto_qa.render_two_lane import render as render_two_lane  # noqa: E402

VLM_LABELS = os.path.join(HERE, "lookalike", "vlm_labels.json")


def load_vlm_labels():
    return json.load(open(VLM_LABELS)) if os.path.exists(VLM_LABELS) else {}

DEFAULT_CSV = os.path.join(ROOT, "BugWood_Diseases_enriched.csv")


def load_rows(csv_path):
    rows = []
    with open(csv_path, newline="") as fh:
        for r in csvmod.DictReader(fh):
            st = decode_state(r.get("Location (State)")) or (r.get("Location") or "").strip()
            crop = (r.get("NormCrop") or "").strip()
            dis = (r.get("NormDisease") or "").strip()
            if not (st and crop and dis and (r.get("Image URL") or "").strip()):
                continue
            if st not in CENSUS_DIVISION:
                continue
            rows.append({
                "img": (r.get("Image Number") or "").strip(),
                "url": (r.get("Image URL") or "").strip(),
                "cite": (r.get("Citation") or "").strip(),
                "state": st, "crop": crop, "disease": dis,
                "host_common": (r.get("Host Name") or crop).strip(),
                "host_sci": (r.get("Host Scientific Name") or "").strip(),
                "path_sci": (r.get("Scientific Name") or "").strip(),
                "path_common": (r.get("Common Name") or "").strip(),
                "descriptor": (r.get("Descriptor Name") or "Symptoms").strip(),
                "koppen_major": (r.get("koppen_major") or "").strip(),
                "photographer": (r.get("Photographer") or "").strip(),
                "org": (r.get("Organization") or "").strip(),
            })
    return rows


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
def build(csv_path, min_imgs, seed, out_path, report=False, max_items=None,
          require_evidence=True, corrections_path=None):
    rows = load_rows(csv_path)
    rng = random.Random(seed)
    split = make_splits(rows, rng)
    train_rows = [r for i, r in enumerate(rows) if split[i] == "train"]
    oracle = GeoOracle(train_rows)

    # S12 prior-audit corrections (optional). Keyed host|true|distractor|region.
    # drop_from_lane_b / relabel  -> drop the Lane-B item (gold not trustworthy as-is);
    # flag                        -> keep but mark gold.low_confidence_prior.
    corrections = {}
    if corrections_path and os.path.exists(corrections_path):
        corrections = json.load(open(corrections_path)).get("corrections", {})
    corr_dropped = corr_flagged = 0

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

    # (crop, disease) -> set of organs the disease is actually photographed on
    # (from the per-image VLM labels). Used to gate Lane B: a look-alike only holds
    # on an organ where BOTH members occur, so the distractor must appear on the
    # photographed organ — otherwise the organ alone rules it out (no geography needed).
    disease_organs = collections.defaultdict(set)
    for (crop, dis), rws in by_cd.items():
        for r in rws:
            v = vlm_labels.get(r["img"])
            if v and v.get("anatomical_part"):
                disease_organs[(crop, dis)].add(v["anatomical_part"].strip().lower())
    laneb_clip_drop = laneb_organ_drop = laneb_noflip_drop = 0

    items = []
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
        # WEB-GATE look-alike confirmation (CLIP no longer vetoes; it routes).
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
                sp = split[idx_of[id(r)]]
                vlm = vlm_labels.get(r["img"])
                it = render_two_lane(rec, g, r, member, oracle, sp, vlm, seed)
                if it is None:                       # dropped (no close-up / no lane / geo not decisive)
                    continue
                # Tighten Lane B: keep ONLY where CLIP and the VLM agree the photo is
                # ambiguous. The VLM already said the deciding sign is not visible (that
                # is why render made it Lane B); now also require the pair's CLIP lane to
                # be image_ambiguous (intrinsically entangled), not image_decisive
                # ("sign exists, just not in THIS photo") — and require the distractor to
                # actually occur on the photographed organ.
                if it.get("lane") == "image_ambiguous":
                    if (evidence or {}).get("clip_lane_hint") != "image_ambiguous":
                        laneb_clip_drop += 1
                        continue
                    dist_disease = mb if member == "a" else ma
                    part = (it["grounding"].get("anatomical_part") or "").strip().lower()
                    dorg = disease_organs.get((p["crop"], dist_disease), set())
                    if part and dorg and part not in dorg:
                        laneb_organ_drop += 1
                        continue
                    # A genuine Lane-B item MUST flip under region swap; if no region
                    # honestly favors the distractor (S13 made it a control), geography
                    # is not actually load-bearing here -> drop, don't ship a contradiction.
                    if it["counterfactual"].get("control"):
                        laneb_noflip_drop += 1
                        continue
                if corrections and it.get("lane") == "image_ambiguous":
                    gd = it["grounding"]; gl = it["gold"]
                    key = f"{gd['host']}|{gl['diagnosis']}|{gl['ruled_out']}|{gd['region']}"
                    c = corrections.get(key)
                    if c:
                        if c["action"] in ("drop_from_lane_b", "relabel"):
                            corr_dropped += 1
                            continue
                        if c["action"] == "flag":
                            gl["low_confidence_prior"] = True
                            corr_flagged += 1
                it["lookalike"]["evidence"] = evidence
                it["_tech_decisive"] = tech[member]   # for anti-leakage check; stripped before write
                items.append(it)
                if max_items and len(items) >= max_items:
                    break
            if max_items and len(items) >= max_items:
                break
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
        "lanes": dict(collections.Counter(it["lane"] for it in items)),
        "counterfactual_controls": sum(1 for it in items if it["counterfactual"]["control"]),
        "lane_b_dropped_clip_disagree": laneb_clip_drop,
        "lane_b_dropped_organ_mismatch": laneb_organ_drop,
        "lane_b_dropped_no_flip": laneb_noflip_drop,
        "audit_corrections_applied": bool(corrections),
        "audit_lane_b_dropped": corr_dropped,
        "audit_lane_b_flagged": corr_flagged,
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
    print(f"  lanes: {summary['lanes']} (counterfactual controls: {summary['counterfactual_controls']})")
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
    """Two-lane gates. The headline is ANTI-LEAKAGE: the graph's *technical*
    decisive sign must never appear in any farmer turn."""
    fails = []
    for it in items:
        iid = it["item_id"]
        farmer = " ".join(t["text"].lower() for t in it["dialogue"] if t["speaker"] == "farmer")
        lane = it.get("lane")
        # 1) ANTI-LEAKAGE: technical decisive sign not handed over by the farmer.
        tech = (it.get("_tech_decisive") or "").lower().strip().rstrip(".")
        if tech and tech in farmer:
            fails.append((iid, "LEAK: technical decisive sign in farmer turn"))
        # 2) CoT ends in CONCLUDE; diagnosis != distractor; diagnosis is a member.
        if not it["cot"] or it["cot"][-1]["step"] != "CONCLUDE":
            fails.append((iid, "no CONCLUDE"))
        if it["gold"]["diagnosis"] == it["lookalike"]["distractor"]:
            fails.append((iid, "diagnosis == distractor"))
        # 3) first farmer turn carries the image.
        if not it["dialogue"][0].get("has_image"):
            fails.append((iid, "F1 has no image"))
        # 4) lane-specific invariants.
        expert = " ".join(t["text"] for t in it["dialogue"] if t["speaker"] == "expert")
        reg = it["grounding"]["region"]
        if lane == "image_decisive":
            if it["gold"]["geography_used"] or not it["gold"]["answerable_from_image"]:
                fails.append((iid, "Lane A: geography flag / not answerable-from-image"))
            if not it["counterfactual"]["control"]:
                fails.append((iid, "Lane A: counterfactual must be control"))
            # the decisive sign must be read FROM the image
            if "READ_SIGN" not in [s["step"] for s in it["cot"]]:
                fails.append((iid, "Lane A: no READ_SIGN step"))
        elif lane == "image_ambiguous":
            if not it["gold"]["geography_used"] or it["gold"]["answerable_from_image"]:
                fails.append((iid, "Lane B: geography not used / claims answerable-from-image"))
            if reg and reg not in expert:
                fails.append((iid, "Lane B: region not used by expert"))
            rp = it["gold"].get("region_prior", {})
            if not (rp.get("true", 0) > rp.get("distractor", 0)):
                fails.append((iid, "Lane B: prior does not favor the gold member"))
            if it["counterfactual"]["control"]:
                fails.append((iid, "Lane B: counterfactual must NOT be control"))
        else:
            fails.append((iid, f"unknown lane {lane}"))
        # 5) look-alike evidence present (WEB GATE — CLIP is a router, not required).
        ev = it["lookalike"].get("evidence")
        if ev is not None and not (ev.get("web_verified") and ev.get("web_source_url")):
            fails.append((iid, "look-alike evidence incomplete (web source missing)"))
    return fails


def _print_sample(it):
    print("\n--- SAMPLE ITEM ---")
    print(f"{it['item_id']}  [{it['split']}]  LANE={it['lane']}  "
          f"{it['lookalike']['true']} vs {it['lookalike']['distractor']}  "
          f"@ {it['grounding']['state']} ({it['grounding']['region']})  part={it['grounding']['anatomical_part']}")
    for t in it["dialogue"]:
        tag = "(img)" if t["has_image"] else "     "
        print(f"  [{t['turn']}]{tag} {t['speaker']:6s}: {t['text']}")
    print("  CoT:")
    for s in it["cot"]:
        print(f"    {s['step']:14s} {s['text']}")
    print(f"  gold: dx={it['gold']['diagnosis']} | geography_used={it['gold']['geography_used']} "
          f"| answerable_from_image={it['gold']['answerable_from_image']}")
    print(f"  counterfactual: control={it['counterfactual']['control']} -> {it['counterfactual']['expected_shift'][:90]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=DEFAULT_CSV)
    ap.add_argument("--min-imgs", type=int, default=12)
    ap.add_argument("--seed", type=int, default=20260613)
    ap.add_argument("--out", default=os.path.join(ROOT, "geophyto_qa.jsonl"))
    ap.add_argument("--max", type=int, default=None, help="cap items (smoke test)")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--no-require-evidence", action="store_true",
                    help="skip the CLIP+web look-alike gate (debug only)")
    ap.add_argument("--corrections", default=None,
                    help="apply S12 prior-audit corrections (lane_b_corrections.json)")
    args = ap.parse_args()
    build(args.csv, args.min_imgs, args.seed, args.out, args.report, args.max,
          require_evidence=not args.no_require_evidence,
          corrections_path=args.corrections)


if __name__ == "__main__":
    main()
