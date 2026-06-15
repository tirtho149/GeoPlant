"""
geophyto_qa.data_source
=======================
One loader for the pipeline's `rows`, from EITHER:

  * a directory of images in ImageFolder layout  <root>/<Host>/<Disease>/<*.jpg>
    (e.g. /work/mech-ai-scratch/tirtho/CyAg/Curated_Dataset/Images), or
  * the legacy Bugwood enriched CSV.

`load_rows(source)` auto-detects. A row is a dict with the fields the rest of the
pipeline uses: img (stable unique id), url (http or local path), crop, disease,
host_common, descriptor, path_sci/path_common, state (provenance only), etc.

Since geography was dropped, the directory loader needs no location data — `state`
is left empty and is used only as image metadata.
"""
from __future__ import annotations

import csv as csvmod
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from utils.geo import decode_state                 # noqa: E402
from geophyto_qa.regions import CENSUS_DIVISION    # noqa: E402

IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


def _disp(name: str) -> str:
    """Folder name -> display label: underscores to spaces."""
    return name.replace("_", " ").strip()


def load_rows_dir(root: str):
    """Scan <root>/<Host>/<Disease>/<*.img> into pipeline rows."""
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


def load_rows_csv(csv_path: str):
    """Legacy Bugwood enriched CSV loader (requires US-state admin1 tier)."""
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


def load_rows(source: str):
    """Auto-detect: a directory -> ImageFolder loader; a file -> Bugwood CSV loader."""
    return load_rows_dir(source) if os.path.isdir(source) else load_rows_csv(source)
