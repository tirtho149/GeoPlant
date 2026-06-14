"""
scripts/enrich_geo_env.py
=========================
Enrich the Bugwood usable CSV with environmental / climate features sampled
from local public rasters (no Earth Engine, no auth, fully reproducible).

Because Bugwood geo is only US-state granularity, every row collapses to one
of ~47 unique (StateLat, StateLon) centroids. We therefore sample each raster
once per unique point and join the result back to all rows.

Rasters expected under data/rasters/ (download via scripts/fetch_rasters.sh):
  wc2.1_10m_bio_1.tif .. wc2.1_10m_bio_19.tif   WorldClim 2.1 bioclim (10 arc-min)
  wc2.1_10m_elev.tif                            WorldClim 2.1 elevation (m)
  koppen_present_1km.tif                         Beck et al. 2023 Köppen-Geiger (1991-2020)
  koppen_present_0p1.tif                         coarse Köppen fallback for nodata points

Adds per row:
  koppen_code      e.g. "Cfa"        (Köppen-Geiger climate class)
  koppen_major     e.g. "C"          (major climate group A/B/C/D/E)
  elev_m           int               (elevation, metres)
  bio1 .. bio19    float             (WorldClim bioclim variables; see BIO_LEGEND)

Usage:
  python scripts/enrich_geo_env.py \
      --input  BugWood_Diseases_usable.csv \
      --output BugWood_Diseases_enriched.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from typing import Dict, List, Optional, Tuple

import rasterio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.geo import state_to_latlon  # noqa: E402

RASTER_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "rasters")

# Beck et al. (2023) Köppen-Geiger integer legend (0 = ocean/nodata).
KOPPEN: Dict[int, str] = {
    1: "Af", 2: "Am", 3: "Aw", 4: "BWh", 5: "BWk", 6: "BSh", 7: "BSk",
    8: "Csa", 9: "Csb", 10: "Csc", 11: "Cwa", 12: "Cwb", 13: "Cwc",
    14: "Cfa", 15: "Cfb", 16: "Cfc", 17: "Dsa", 18: "Dsb", 19: "Dsc",
    20: "Dsd", 21: "Dwa", 22: "Dwb", 23: "Dwc", 24: "Dwd", 25: "Dfa",
    26: "Dfb", 27: "Dfc", 28: "Dfd", 29: "ET", 30: "EF",
}

BIO_LEGEND = {
    "bio1": "Annual Mean Temperature (C)",
    "bio2": "Mean Diurnal Range (C)",
    "bio3": "Isothermality (bio2/bio7 x100)",
    "bio4": "Temperature Seasonality (std x100)",
    "bio5": "Max Temperature of Warmest Month (C)",
    "bio6": "Min Temperature of Coldest Month (C)",
    "bio7": "Temperature Annual Range (C)",
    "bio8": "Mean Temperature of Wettest Quarter (C)",
    "bio9": "Mean Temperature of Driest Quarter (C)",
    "bio10": "Mean Temperature of Warmest Quarter (C)",
    "bio11": "Mean Temperature of Coldest Quarter (C)",
    "bio12": "Annual Precipitation (mm)",
    "bio13": "Precipitation of Wettest Month (mm)",
    "bio14": "Precipitation of Driest Month (mm)",
    "bio15": "Precipitation Seasonality (CV)",
    "bio16": "Precipitation of Wettest Quarter (mm)",
    "bio17": "Precipitation of Driest Quarter (mm)",
    "bio18": "Precipitation of Warmest Quarter (mm)",
    "bio19": "Precipitation of Coldest Quarter (mm)",
}

NEW_COLS = ["koppen_code", "koppen_major", "elev_m"] + [f"bio{i}" for i in range(1, 20)]


def _r(name: str) -> str:
    p = os.path.join(RASTER_DIR, name)
    if not os.path.isfile(p):
        raise SystemExit(f"missing raster: {p}\n  run scripts/fetch_rasters.sh first")
    return p


def _sample_koppen(ds_fine, ds_coarse, lon: float, lat: float) -> int:
    """Köppen integer at the point; fall back to the coarse map if fine is nodata."""
    v = int(list(ds_fine.sample([(lon, lat)]))[0][0])
    if v == 0:
        v = int(list(ds_coarse.sample([(lon, lat)]))[0][0])
    return v


def enrich(input_csv: str, output_csv: str) -> None:
    # ---- open rasters once ----
    bios = {i: rasterio.open(_r(f"wc2.1_10m_bio_{i}.tif")) for i in range(1, 20)}
    elev = rasterio.open(_r("wc2.1_10m_elev.tif"))
    kop_fine = rasterio.open(_r("koppen_present_1km.tif"))
    kop_coarse = rasterio.open(_r("koppen_present_0p1.tif"))
    bio_nodata = {i: bios[i].nodata for i in bios}

    # ---- read rows, collect unique points (prefer CSV lat/lon, else derive) ----
    with open(input_csv, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    def point_of(row: dict) -> Optional[Tuple[float, float]]:
        slat, slon = row.get("StateLat"), row.get("StateLon")
        try:
            if slat and slon:
                return float(slat), float(slon)
        except ValueError:
            pass
        lat, lon = state_to_latlon(row.get("Location", ""))
        return (lat, lon) if lat is not None else None

    uniq: Dict[Tuple[float, float], Dict[str, str]] = {}
    for row in rows:
        pt = point_of(row)
        if pt and pt not in uniq:
            uniq[pt] = {}

    # ---- sample each unique point once ----
    for (lat, lon) in uniq:
        feat: Dict[str, str] = {}
        kv = _sample_koppen(kop_fine, kop_coarse, lon, lat)
        code = KOPPEN.get(kv, "")
        feat["koppen_code"] = code
        feat["koppen_major"] = code[0] if code else ""
        ev = int(list(elev.sample([(lon, lat)]))[0][0])
        feat["elev_m"] = "" if ev == elev.nodata else str(ev)
        for i in range(1, 20):
            val = float(list(bios[i].sample([(lon, lat)]))[0][0])
            nd = bio_nodata[i]
            feat[f"bio{i}"] = "" if (nd is not None and val == nd) else f"{val:.3f}"
        uniq[(lat, lon)] = feat

    # ---- join back + write ----
    out_fields = fieldnames + [c for c in NEW_COLS if c not in fieldnames]
    n_enriched = 0
    with open(output_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=out_fields)
        writer.writeheader()
        for row in rows:
            pt = point_of(row)
            feat = uniq.get(pt) if pt else None
            if feat:
                row.update(feat)
                n_enriched += 1
            else:
                for c in NEW_COLS:
                    row.setdefault(c, "")
            writer.writerow(row)

    # ---- sidecar legend + per-point table ----
    legend_path = os.path.join(os.path.dirname(output_csv) or ".", "geo_env_legend.json")
    with open(legend_path, "w", encoding="utf-8") as fh:
        json.dump({"bio": BIO_LEGEND, "koppen": KOPPEN,
                   "sources": {
                       "bioclim_elev": "WorldClim 2.1, 10 arc-min",
                       "koppen": "Beck et al. 2023, Koppen-Geiger 1991-2020"}},
                  fh, indent=2)

    print(f"input:   {input_csv} ({len(rows)} rows)")
    print(f"output:  {output_csv} ({n_enriched} rows enriched, "
          f"{len(rows) - n_enriched} with no geo)")
    print(f"points:  {len(uniq)} unique centroids sampled")
    print(f"columns: +{len(NEW_COLS)} ({', '.join(NEW_COLS[:5])} ... bio19)")
    print(f"legend:  {legend_path}")
    # quick distribution
    from collections import Counter
    dist = Counter(uniq[p]["koppen_code"] for p in uniq)
    print("koppen across points:", dict(sorted(dist.items(), key=lambda kv: -kv[1])))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument("--input", default="BugWood_Diseases_usable.csv")
    p.add_argument("--output", default="BugWood_Diseases_enriched.csv")
    return p.parse_args()


if __name__ == "__main__":
    a = parse_args()
    enrich(a.input, a.output)
