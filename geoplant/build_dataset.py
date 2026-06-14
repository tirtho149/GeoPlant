"""
geoplant.build_dataset
======================
End-to-end builder for the GeoPlantPath geospatial plant-disease dataset.

Pipeline:
  1. load a scraped Bugwood CSV (geoplant.scrape.bugwood_scraper output, with
     Date Taken / County / Lat / Lon), or fall back to the legacy
     BugWood_Diseases.csv;
  2. resolve every row to (lat, lon, geo_precision) via the priority ladder
     point > county > state (geoplant.geocode.county_centroids);
  3. derive temporal fields (year / month / season) from Date Taken;
  4. sample environmental features at the unique points:
       - local rasters  (bioclim / Köppen / elevation)        [always, no auth]
       - Earth Engine   (land cover / soil / NDVI / water bal) [--backend gee]
  5. join back to all rows and write the enriched CSV + legend.

Usage:
  python -m geoplant.build_dataset --input bugwood_disease_scraped.csv \
      --output BugWood_Diseases_geoenriched.csv --backend local
  python -m geoplant.build_dataset --backend gee     # add Earth Engine layers
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from collections import Counter
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from geoplant.config import (BIO_LEGEND, ENRICHED_CSV, KOPPEN, LEGEND_JSON,
                             SCRAPED_CSV, WORLDCOVER_LEGEND)
from geoplant.enrich import local_rasters
from geoplant.geocode.county_centroids import resolve_point

GEO_COLS = ["geo_lat", "geo_lon", "geo_precision", "geo_source"]
TIME_COLS = ["year", "month", "season"]

_DATE_FORMATS = ["%m/%d/%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S.%fZ", "%m/%d/%y"]


def parse_date(s: str) -> Optional[datetime]:
    s = (s or "").strip()
    if not s:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def season_of(month: int, lat: float) -> str:
    """Meteorological season, hemisphere-aware."""
    north = {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring",
             5: "spring", 6: "summer", 7: "summer", 8: "summer", 9: "autumn",
             10: "autumn", 11: "autumn"}
    s = north.get(month, "")
    if lat is not None and lat < 0 and s:  # flip for southern hemisphere
        s = {"winter": "summer", "summer": "winter",
             "spring": "autumn", "autumn": "spring"}[s]
    return s


def temporal_fields(row: dict, lat: Optional[float]) -> Dict[str, str]:
    dt = parse_date(row.get("Date Taken", "")) or None
    if dt is None:
        return {"year": "", "month": "", "season": ""}
    return {"year": str(dt.year), "month": str(dt.month),
            "season": season_of(dt.month, lat if lat is not None else 0.0)}


def load_rows(path: str) -> Tuple[List[dict], List[str]]:
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return list(reader), list(reader.fieldnames or [])


def build(input_csv: str, output_csv: str, backend: str = "local") -> None:
    rows, fieldnames = load_rows(input_csv)
    print(f"loaded {len(rows)} rows from {input_csv}")

    # ---- resolve geo + temporal per row, collect unique points ----
    prec_counter = Counter()
    points: List[Tuple[float, float]] = []
    for row in rows:
        lat, lon, prec, src = resolve_point(row)
        row["geo_lat"] = "" if lat is None else f"{lat:.6f}"
        row["geo_lon"] = "" if lon is None else f"{lon:.6f}"
        row["geo_precision"] = prec
        row["geo_source"] = src
        row.update(temporal_fields(row, lat))
        prec_counter[prec] += 1
        if lat is not None:
            points.append((lat, lon))
    uniq = list(dict.fromkeys(points))
    print(f"resolved geo: {dict(prec_counter)} | {len(uniq)} unique points")

    # ---- sample environmental features ----
    print(f"sampling local rasters at {len(uniq)} points ...")
    local_feat = local_rasters.sample_points(uniq)
    env_cols = list(local_rasters.LOCAL_COLS)

    gee_feat: Dict[Tuple[float, float], Dict[str, str]] = {}
    if backend in ("gee", "gee-full"):
        from geoplant.enrich import gee
        specs = None  # default EE_EXTRA_SPECS
        if backend == "gee-full":
            from geoplant.config import EE_BIO_SPECS, EE_EXTRA_SPECS
            specs = EE_EXTRA_SPECS + EE_BIO_SPECS
        print("sampling Earth Engine layers ...")
        gee_feat = gee.sample_points(uniq, specs=specs)
        env_cols += gee.ee_columns(specs)

    # ---- join back ----
    new_cols = GEO_COLS + TIME_COLS + env_cols
    out_fields = fieldnames + [c for c in new_cols if c not in fieldnames]
    n_env = 0
    with open(output_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=out_fields)
        writer.writeheader()
        for row in rows:
            key = None
            if row["geo_lat"]:
                key = (float(row["geo_lat"]), float(row["geo_lon"]))
            feat = {}
            if key is not None:
                feat.update(local_feat.get(key, {}))
                feat.update(gee_feat.get(key, {}))
            if feat:
                n_env += 1
            for c in env_cols:
                row[c] = feat.get(c, "")
            writer.writerow(row)

    # ---- legend + summary ----
    legend = {"bio": BIO_LEGEND, "koppen": KOPPEN,
              "worldcover": WORLDCOVER_LEGEND,
              "geo_precision": "point>county>state ladder",
              "sources": {"bioclim_elev": "WorldClim 2.1 (10 arc-min)",
                          "koppen": "Beck et al. 2023 (1991-2020)",
                          "county": "US Census 2023 Gazetteer",
                          "gee": "Earth Engine (worldcover/terraclimate/ndvi/soil)"}}
    with open(LEGEND_JSON, "w", encoding="utf-8") as fh:
        json.dump(legend, fh, indent=2)

    print(f"\n✓ wrote {output_csv}")
    print(f"  rows={len(rows)} | env-enriched={n_env} | +{len(new_cols)} columns")
    print(f"  precision: {dict(prec_counter)}")
    print(f"  legend: {LEGEND_JSON}")


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    default_in = SCRAPED_CSV if os.path.isfile(SCRAPED_CSV) else "BugWood_Diseases.csv"
    ap.add_argument("--input", default=default_in)
    ap.add_argument("--output", default=ENRICHED_CSV)
    ap.add_argument("--backend", choices=["local", "gee", "gee-full"], default="local")
    return ap.parse_args()


if __name__ == "__main__":
    a = parse_args()
    build(a.input, a.output, a.backend)
