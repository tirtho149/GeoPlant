"""
geoplant.config
===============
Central paths + dataset/enrichment configuration for the GeoPlantPath
(GeoPhyto-CoT) geospatial plant-disease dataset builder.

Nothing here requires Earth Engine; the EE project id is only read when the
GEE enrichment backend is actually used.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
RASTERS = os.path.join(DATA, "rasters")

# Earth Engine cloud project — set GEE_PROJECT or EARTHENGINE_PROJECT in env.
GEE_PROJECT = os.environ.get("GEE_PROJECT") or os.environ.get("EARTHENGINE_PROJECT", "")

# Default I/O artefacts of the pipeline.
RAW_CSV = os.path.join(ROOT, "BugWood_Diseases.csv")
SCRAPED_CSV = os.path.join(ROOT, "bugwood_disease_scraped.csv")
POINTS_CSV = os.path.join(DATA, "geo_points.csv")          # unique points to sample
ENRICHED_CSV = os.path.join(ROOT, "BugWood_Diseases_geoenriched.csv")
LEGEND_JSON = os.path.join(ROOT, "geo_env_legend.json")


# ---------------------------------------------------------------------------
# Earth Engine enrichment specs.
#
# Each spec describes how to turn an EE dataset into a flat set of point
# features. `image` is built lazily inside geoplant.enrich.gee (so importing
# this module never touches Earth Engine). `bands` are renamed to the given
# output column names; `scale` is the sampling scale in metres.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EESpec:
    key: str                       # short id, used in logs
    asset: str                     # EE ImageCollection / Image id
    bands: Dict[str, str]          # ee_band_name -> output_column
    scale: int                     # sampling scale (m)
    reducer: str = "mean"          # spatial reducer over the sample footprint
    temporal: str = ""             # "" = Image; "mean"/"median" = reduce an ImageCollection
    start: str = ""                # temporal filter start (YYYY-MM-DD)
    end: str = ""                  # temporal filter end
    scale_factor: float = 1.0      # multiply sampled value (apply dataset scale)


# Layers EE uniquely adds on top of the local-raster bioclim/Köppen/elevation.
# This is the default enrichment when the GEE backend is enabled.
EE_EXTRA_SPECS: List[EESpec] = [
    # ESA WorldCover 2021 land-cover class (10 m, categorical -> use mode).
    EESpec(
        key="worldcover",
        asset="ESA/WorldCover/v200",
        bands={"Map": "landcover_esa"},
        scale=100, reducer="mode", temporal="mosaic",
    ),
    # TerraClimate annual water balance (4638 m), averaged over a recent decade.
    EESpec(
        key="terraclimate",
        asset="IDAHO_EPSCOR/TERRACLIMATE",
        bands={"aet": "tc_aet", "def": "tc_def", "pdsi": "tc_pdsi",
               "soil": "tc_soilmoist", "pr": "tc_precip"},
        scale=4638, reducer="mean", temporal="mean",
        start="2010-01-01", end="2020-01-01",
    ),
    # MODIS NDVI (1 km), mean over a recent decade, scaled to real NDVI.
    EESpec(
        key="ndvi",
        asset="MODIS/061/MOD13A2",
        bands={"NDVI": "ndvi_mean"},
        scale=1000, reducer="mean", temporal="mean",
        start="2010-01-01", end="2020-01-01", scale_factor=0.0001,
    ),
    # OpenLandMap soil pH at 0 cm (250 m).
    EESpec(
        key="soil_ph",
        asset="OpenLandMap/SOL/SOL_PH-H2O_USDA-4C1A2A_M/v02",
        bands={"b0": "soil_ph_h2o"},
        scale=250, reducer="mean", scale_factor=0.1,
    ),
    # OpenLandMap soil organic carbon at 0 cm (250 m).
    EESpec(
        key="soil_oc",
        asset="OpenLandMap/SOL/SOL_ORGANIC-CARBON_USDA-6A1C_M/v02",
        bands={"b0": "soil_organic_carbon"},
        scale=250, reducer="mean", scale_factor=5.0,
    ),
]

# Optional all-EE bioclim/elevation (use --backend gee-full). WorldClim V1 in EE
# stores temperature-derived bands x0.1; we leave them raw and document it rather
# than guess per-band scales — the local-raster path (WorldClim 2.1) is canonical.
EE_BIO_SPECS: List[EESpec] = [
    EESpec(key="worldclim_bio", asset="WORLDCLIM/V1/BIO",
           bands={f"bio{n:02d}": f"bio{n}_ee" for n in range(1, 20)},
           scale=1000, reducer="mean"),
    EESpec(key="elevation", asset="USGS/SRTMGL1_003",
           bands={"elevation": "elev_m_ee"}, scale=90, reducer="mean"),
]

# ESA WorldCover v200 class legend (band "Map").
WORLDCOVER_LEGEND: Dict[int, str] = {
    10: "Tree cover", 20: "Shrubland", 30: "Grassland", 40: "Cropland",
    50: "Built-up", 60: "Bare/sparse veg", 70: "Snow and ice",
    80: "Permanent water", 90: "Herbaceous wetland", 95: "Mangroves",
    100: "Moss and lichen",
}


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
