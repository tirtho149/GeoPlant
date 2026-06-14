#!/usr/bin/env bash
# Fetch the public environmental rasters used by scripts/enrich_geo_env.py.
# No auth / no Earth Engine. ~54 MB on disk after cleanup.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data/rasters && cd data/rasters

echo "[1/3] WorldClim 2.1 bioclim (10 arc-min)"
curl -L -o wc2.1_10m_bio.zip  "https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_10m_bio.zip"
unzip -o wc2.1_10m_bio.zip && rm -f wc2.1_10m_bio.zip

echo "[2/3] WorldClim 2.1 elevation"
curl -L -o wc2.1_10m_elev.zip "https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_10m_elev.zip"
unzip -o wc2.1_10m_elev.zip && rm -f wc2.1_10m_elev.zip

echo "[3/3] Koppen-Geiger 1991-2020 (Beck et al. 2023, figshare 21789074)"
curl -L -o koppen_geiger_tif.zip "https://figshare.com/ndownloader/files/61012822"
unzip -o koppen_geiger_tif.zip "1991_2020/koppen_geiger_0p00833333.tif" "1991_2020/koppen_geiger_0p1.tif"
mv -f 1991_2020/koppen_geiger_0p00833333.tif koppen_present_1km.tif
mv -f 1991_2020/koppen_geiger_0p1.tif        koppen_present_0p1.tif
rmdir 1991_2020 2>/dev/null || true
rm -f koppen_geiger_tif.zip

echo "done. rasters in $(pwd)"
