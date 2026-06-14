# GeoPlantPath — Geospatial Plant-Disease Dataset Builder

Code that turns Bugwood disease imagery into the **GeoPhyto-CoT** geospatial
dataset: each image carries host + disease labels, the best available location
(point → county → state), a capture date when known, and a stack of
environmental / climate features sampled at that location.

See `geophyto-cot-wacv-outline.md` for the paper framing this feeds.

---

## Pipeline at a glance

```
Bugwood API  ──scrape──▶  scraped CSV  ──resolve──▶  (lat,lon,precision)+date
   (v2)                   (host/disease/             │
                           location/date)            ├─ local rasters (no auth)
                                                      │     bioclim·köppen·elev
                                                      └─ Earth Engine (opt, auth)
                                                            landcover·soil·ndvi·waterbal
                                                                    │
                                                                    ▼
                                                        BugWood_Diseases_geoenriched.csv
```

Package layout (`geoplant/`):

| module | role |
|--------|------|
| `config.py` | paths, EE project id, EE dataset specs, legends |
| `scrape/bugwood_scraper.py` | extended Bugwood scraper (adds date/county/lat-lon) |
| `geocode/county_centroids.py` | row → (lat,lon,precision) via point>county>state ladder |
| `enrich/local_rasters.py` | sample WorldClim/Köppen/elevation GeoTIFFs (no auth) |
| `enrich/gee.py` | sample Earth Engine layers (needs auth) |
| `build_dataset.py` | end-to-end orchestrator |

---

## 1. Scrape (adds the geo/temporal fields the first export dropped)

```bash
python -m geoplant.scrape.bugwood_scraper --max-pages 0 \
    --output bugwood_disease_scraped.csv          # full run (all pages)
python -m geoplant.scrape.bugwood_scraper --max-pages 1 --limit 150 \
    --output /tmp/smoke.csv                        # quick test
```

New columns over the legacy CSV: `Country, State, County, Lat, Lon,
Date Taken, Date Acquired`.

**Coverage reality (measured on plant-disease categories):**

| field | fill rate | note |
|-------|-----------|------|
| `Date Acquired` | ~100% | upload timestamp, *not* capture date |
| `Date Taken` | ~15–25% | true capture date; used for year/month/season |
| `County` | ~5–6% | enables county-centroid geo |
| `Lat`/`Lon` | ~1–3% | exact point geo when present |

So US-**state** is the common geographic tier; county/point refine the minority
that carry finer metadata. Time is a partial signal — present on ~1 in 5 images.

## 2. Local-raster enrichment (default, no auth)

Download the public rasters once:

```bash
bash scripts/fetch_rasters.sh          # WorldClim 2.1 bio+elev, Köppen-Geiger 2023
```

Adds per row: `koppen_code, koppen_major, elev_m, bio1..bio19`
(see `geo_env_legend.json`). Sources: WorldClim 2.1 (10′), Beck et al. 2023 Köppen.

## 3. Build the dataset

```bash
python -m geoplant.build_dataset \
    --input bugwood_disease_scraped.csv \
    --output BugWood_Diseases_geoenriched.csv --backend local
```

Adds `geo_lat, geo_lon, geo_precision, geo_source, year, month, season` plus the
environmental columns. `geo_precision ∈ {point, county, state, none}` is the
honesty flag for downstream geolocation evaluation.

---

## 4. Earth Engine enrichment (optional, richer — needs your auth)

EE adds layers the local rasters don't have: ESA WorldCover land cover,
TerraClimate water balance (AET / climatic deficit / PDSI / soil moisture /
precip), MODIS NDVI, and OpenLandMap soil pH + organic carbon — all sampled at
the same resolved points.

**One-time setup (must be done by you — interactive):**

```bash
pip install earthengine-api            # already in the venv
earthengine authenticate               # browser / paste-code OAuth
export GEE_PROJECT=your-ee-cloud-project   # a registered Earth Engine project
```

Then:

```bash
python -m geoplant.build_dataset --backend gee        # local + EE extra layers
python -m geoplant.build_dataset --backend gee-full   # also bioclim/elev from EE
```

How it samples (in `enrich/gee.py`): the unique points become one
`ee.FeatureCollection`; each dataset (`config.EE_EXTRA_SPECS`) is reduced to a
single multi-band image (temporal mean for collections) and sampled with
`image.reduceRegions(points, reducer, scale)` — one server call per layer,
pulled back with a single `getInfo()`. Add/remove layers by editing
`EESpec` entries in `config.py`; no other code changes needed.

> Why local is the default: with only ~tens of unique centroids, EE's
> per-pixel precision is largely wasted, and a benchmark that re-runs without a
> Google account is more reproducible. EE is the *enhancement*, not the base.

---

## How columns map to the GeoPhyto-CoT outline

| outline need | column(s) | from |
|--------------|-----------|------|
| host / disease labels | `Host Name`, `Subject Display Name`, `Scientific Name` | scrape |
| location @ tier | `geo_lat/lon`, `geo_precision`, `State`, `County` | geocode |
| date | `Date Taken`, `year`, `month`, `season` | scrape + derive |
| climate zone (Köppen) | `koppen_code`, `koppen_major` | local raster |
| climate features (NARROW step) | `bio1..bio19`, `elev_m`, `tc_*`, `ndvi_mean`, `soil_*` | raster + EE |
| land context | `landcover_esa` | EE |

`geo_precision` is what keeps the benchmark honest: rows tagged `state` cannot be
scored at sub-state granularity, and the climate features on them are
state-centroid approximations.
```
