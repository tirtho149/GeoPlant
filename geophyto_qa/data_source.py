"""
geophyto_qa.data_source
=======================
The pipeline's single data source: an **ImageFolder** dataset laid out as

    <root>/<Host>/<Disease>/<*.jpg>

(default: the CyAg curated dataset). The legacy Bugwood enriched-CSV path has been
removed entirely — every step (mine / confusability / vlm / build) now reads
images off local disk through this module. Point GPQA_SOURCE at another directory
to switch datasets.

A row is the unit the rest of the pipeline consumes:
  img          stable unique id  "<Host>__<Disease>__<stem>"
  url          local absolute image path
  crop         host (display)        disease   disease (display)
  host_common  = crop               photographer  source-dataset prefix of the file
  descriptor   "Symptoms" (no organ metadata in an ImageFolder)
"""
from __future__ import annotations

import collections
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}

# The active dataset. Default = CyAg curated ImageFolder; override with GPQA_SOURCE.
CYAG_DEFAULT = "/work/mech-ai-scratch/tirtho/CyAg/Curated_Dataset/Images"
DEFAULT_SOURCE = os.environ.get("GPQA_SOURCE", CYAG_DEFAULT)


def _disp(name: str) -> str:
    """Folder name -> display label: underscores to spaces."""
    return name.replace("_", " ").strip()


def load_rows(source: str = None):
    """Scan <root>/<Host>/<Disease>/<*.img> into pipeline rows. Defaults to
    DEFAULT_SOURCE (GPQA_SOURCE env, else the CyAg curated dataset)."""
    root = source or DEFAULT_SOURCE
    rows = []
    for host in sorted(os.scandir(root), key=lambda d: d.name):
        if not host.is_dir():
            continue
        crop = _disp(host.name)
        for dis in os.scandir(host.path):
            if not dis.is_dir():
                continue
            disease = _disp(dis.name)
            for f in os.scandir(dis.path):
                if not f.is_file() or os.path.splitext(f.name)[1].lower() not in IMG_EXTS:
                    continue
                stem = os.path.splitext(f.name)[0]
                src = stem.split("_")[0]                    # source-dataset prefix
                rows.append({
                    "img": f"{host.name}__{dis.name}__{stem}",   # stable, unique, slug-safe
                    "url": f.path,                               # local absolute path
                    "cite": f"{src} (CyAg curated)",
                    "state": "", "crop": crop, "disease": disease,
                    "host_common": crop, "host_sci": "",
                    "path_sci": "", "path_common": "",
                    "descriptor": "Symptoms", "koppen_major": "",
                    "photographer": src, "org": "CyAg curated",
                })
    return rows


# --------------------------------------------------------------------------- #
# Shared helpers so the image steps (clip/flava confusability, vlm_label) are
# source-agnostic: they read images off disk, never download-by-number.
def organ_bucket_of(descriptor: str) -> str:
    """Descriptor -> coarse organ bucket (lazy import to keep the CPU loaders
    free of the numpy dependency at import time)."""
    from geophyto_qa.lookalike.clip_confuse import organ_bucket
    return organ_bucket(descriptor or "Symptoms")


def load_class_images(source: str = None, cap: int = None):
    """{(crop, disease): [(img_id, organ_bucket), ...]}. Deterministic head sample
    when cap is set."""
    by = collections.defaultdict(list)
    for r in load_rows(source):
        by[(r["crop"], r["disease"])].append(
            (r["img"], organ_bucket_of(r.get("descriptor", "Symptoms"))))
    if cap:
        by = {k: sorted(v)[:cap] for k, v in by.items()}
    return dict(by)


def fetch_locator(source: str = None):
    """{img_id: local image path} for the image steps to load from disk."""
    return {r["img"]: r["url"] for r in load_rows(source)}


def read_image_bytes(loc: str, timeout: float = 15.0):
    """Read raw image bytes from a local path (or http(s) URL), or None on error."""
    try:
        if loc.startswith(("http://", "https://")):
            import urllib.request
            req = urllib.request.Request(loc, headers={"User-Agent": "geophyto-qa/1.0"})
            return urllib.request.urlopen(req, timeout=timeout).read()
        with open(loc, "rb") as fh:
            return fh.read()
    except Exception:
        return None
