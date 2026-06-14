"""
geoplant.enrich.gee
===================
Earth Engine enrichment backend (proper, batched point sampling).

This adds layers that the local rasters don't carry — land cover, soil,
NDVI, and a climatic water balance — by sampling Earth Engine ImageCollections
at the resolved geo-points.

Design (per EE best practice for a few hundred points):
  * points become one ee.FeatureCollection with a stable "pid" property;
  * each EESpec is reduced to a single multi-band ee.Image
    (temporal reduction for collections), renamed to output columns;
  * `image.reduceRegions(points, reducer, scale)` samples all points for that
    layer in one server call; results are pulled with a single getInfo().

AUTH (one-time, done by the user — this code can't do it for you):
    pip install earthengine-api            # already installed in the venv
    earthengine authenticate               # opens browser / paste-code flow
    export GEE_PROJECT=your-ee-cloud-project   # a registered EE Cloud project

Then ee.Initialize(project=GEE_PROJECT) succeeds and sampling runs.

Entry point:
    sample_points(points, specs=None) -> {(lat, lon): {col: value, ...}}
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple

from geoplant.config import EE_EXTRA_SPECS, GEE_PROJECT, EESpec

_REDUCERS = {}  # filled lazily after ee import


def _ensure_ee():
    try:
        import ee  # noqa: F401
    except ImportError as e:
        raise SystemExit("earthengine-api not installed: pip install earthengine-api") from e
    import ee
    try:
        ee.Initialize(project=GEE_PROJECT or None)
    except Exception as e:
        raise SystemExit(
            "Earth Engine not initialised. Run `earthengine authenticate` and set "
            f"GEE_PROJECT to a registered EE Cloud project.\n  underlying error: {e}"
        ) from e
    return ee


def _spec_image(ee, spec: EESpec):
    """Build a single renamed multi-band ee.Image for one spec."""
    if spec.temporal in ("", None):
        img = ee.Image(spec.asset)
    elif spec.temporal == "mosaic":
        img = ee.ImageCollection(spec.asset).mosaic()
    else:  # temporal reduction over a date range
        col = ee.ImageCollection(spec.asset)
        if spec.start and spec.end:
            col = col.filterDate(spec.start, spec.end)
        img = getattr(col, spec.temporal)()  # .mean() / .median()
    in_bands = list(spec.bands.keys())
    out_bands = [spec.bands[b] for b in in_bands]
    img = img.select(in_bands).rename(out_bands)
    if spec.scale_factor != 1.0:
        img = img.multiply(spec.scale_factor).rename(out_bands)
    return img


def _reducer(ee, name: str):
    return {
        "mean": ee.Reducer.mean(),
        "median": ee.Reducer.median(),
        "mode": ee.Reducer.mode(),
        "first": ee.Reducer.first(),
    }.get(name, ee.Reducer.mean())


def sample_points(points: Iterable[Tuple[float, float]],
                  specs: Optional[List[EESpec]] = None
                  ) -> Dict[Tuple[float, float], Dict[str, str]]:
    ee = _ensure_ee()
    specs = specs if specs is not None else EE_EXTRA_SPECS

    pts = list(dict.fromkeys(points))
    feats = [ee.Feature(ee.Geometry.Point([lon, lat]), {"pid": i})
             for i, (lat, lon) in enumerate(pts)]
    fc = ee.FeatureCollection(feats)

    out: Dict[Tuple[float, float], Dict[str, str]] = {p: {} for p in pts}
    for spec in specs:
        img = _spec_image(ee, spec)
        sampled = img.reduceRegions(
            collection=fc, reducer=_reducer(ee, spec.reducer), scale=spec.scale
        ).getInfo()
        out_cols = list(spec.bands.values())
        for f in sampled["features"]:
            props = f["properties"]
            pid = int(props["pid"])
            lat, lon = pts[pid]
            for c in out_cols:
                v = props.get(c)
                out[(lat, lon)][c] = "" if v is None else (
                    f"{v:.4f}" if isinstance(v, float) else str(v))
        print(f"  [gee] {spec.key:14s} sampled {len(pts)} pts -> {out_cols}")
    return out


def ee_columns(specs: Optional[List[EESpec]] = None) -> List[str]:
    specs = specs if specs is not None else EE_EXTRA_SPECS
    cols: List[str] = []
    for s in specs:
        cols.extend(s.bands.values())
    return cols
