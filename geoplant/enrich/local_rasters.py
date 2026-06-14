"""
geoplant.enrich.local_rasters
=============================
No-auth environmental enrichment by sampling local public GeoTIFFs at points.

Provides bioclim (WorldClim 2.1, 19 vars), elevation, and Köppen-Geiger class
(Beck et al. 2023). Download the rasters once with scripts/fetch_rasters.sh.

Primary entry point:
    sample_points(points) -> {(lat, lon): {col: value, ...}}
where `points` is an iterable of (lat, lon) tuples.
"""

from __future__ import annotations

import os
from typing import Dict, Iterable, Tuple

import rasterio

from geoplant.config import KOPPEN, RASTERS

LOCAL_COLS = ["koppen_code", "koppen_major", "elev_m"] + [f"bio{i}" for i in range(1, 20)]


def _r(name: str) -> str:
    p = os.path.join(RASTERS, name)
    if not os.path.isfile(p):
        raise SystemExit(f"missing raster: {p}\n  run scripts/fetch_rasters.sh first")
    return p


def _sample_koppen(ds_fine, ds_coarse, lon: float, lat: float) -> int:
    v = int(list(ds_fine.sample([(lon, lat)]))[0][0])
    if v == 0:
        v = int(list(ds_coarse.sample([(lon, lat)]))[0][0])
    return v


def sample_points(points: Iterable[Tuple[float, float]]
                  ) -> Dict[Tuple[float, float], Dict[str, str]]:
    bios = {i: rasterio.open(_r(f"wc2.1_10m_bio_{i}.tif")) for i in range(1, 20)}
    elev = rasterio.open(_r("wc2.1_10m_elev.tif"))
    kop_fine = rasterio.open(_r("koppen_present_1km.tif"))
    kop_coarse = rasterio.open(_r("koppen_present_0p1.tif"))

    out: Dict[Tuple[float, float], Dict[str, str]] = {}
    for (lat, lon) in dict.fromkeys(points):  # dedupe, keep order
        feat: Dict[str, str] = {}
        kv = _sample_koppen(kop_fine, kop_coarse, lon, lat)
        code = KOPPEN.get(kv, "")
        feat["koppen_code"] = code
        feat["koppen_major"] = code[0] if code else ""
        ev = int(list(elev.sample([(lon, lat)]))[0][0])
        feat["elev_m"] = "" if ev == elev.nodata else str(ev)
        for i in range(1, 20):
            val = float(list(bios[i].sample([(lon, lat)]))[0][0])
            nd = bios[i].nodata
            feat[f"bio{i}"] = "" if (nd is not None and val == nd) else f"{val:.3f}"
        out[(lat, lon)] = feat
    return out
