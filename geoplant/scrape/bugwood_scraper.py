"""
geoplant.scrape.bugwood_scraper
===============================
Extended Bugwood disease scraper.

Over the original scraper this additionally captures the geo/temporal fields
that the Bugwood detail API exposes but the first version dropped:

    Date Taken      detail["datetaken"]      (true capture date, ~16% filled)
    Date Acquired   detail["dateacquired"]   (upload timestamp, ~100% filled)
    Country/State/County   parsed from detail["location"] ("US, Alabama, Calhoun County")
    Lat / Lon       detail["lat"], detail["lon"]   (rarely populated, ~1%)

API: https://api.bugwoodcloud.org/v2

Run:
    python -m geoplant.scrape.bugwood_scraper --max-pages 1          # smoke
    python -m geoplant.scrape.bugwood_scraper --max-pages 0 \
        --output bugwood_disease_scraped.csv                          # full run
"""

from __future__ import annotations

import argparse
import re
import time

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE = "https://api.bugwoodcloud.org/v2"
SLEEP_BETWEEN_DETAIL_CALLS = 0.1

session = requests.Session()
session.headers.update({"accept": "application/json", "user-agent": "Mozilla/5.0"})
session.mount("https://", HTTPAdapter(max_retries=Retry(
    total=5, backoff_factor=1.0,
    status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"])))

# Plant-disease categories (insects/animals excluded; cat 63 "Diseases of
# Insects" deliberately dropped for the plant-disease dataset).
DISEASE_CATEGORIES = {
    8: "Broom Rusts", 13: "Vascular Wilts", 16: "Foliage Diseases",
    35: "Root and Butt / Root and Stem Diseases", 41: "Stem Decays and Cankers",
    42: "Stem and Leaf Rusts", 88: "Virus and Bacteria",
    115: "Fruit and Seed Diseases", 116: "Soft Rot", 122: "Physiological Disorders",
    125: "Decline Complexes", 126: "Smuts", 127: "Root Rot", 129: "Heartrot",
    130: "Nutrient Deficiency", 131: "Nutrient Toxicity", 136: "Storage Diseases",
    137: "Storage Physiological Disorders",
}

RESOLUTION_PATH = {1: "192x128", 2: "384x256", 3: "768x512",
                   4: "1536x1024", 5: "3072x2048"}

COLUMN_ORDER = [
    "Category ID", "Category Name",
    "Image Number", "Scientific Name", "Common Name",
    "Subject Display Name", "Host Name", "Host Scientific Name",
    "Descriptor Name", "Description",
    "Photographer", "Organization", "Orientation", "Citation",
    "Max Resolution", "Image URL",
    # --- geo / temporal (new) ---
    "Location", "Country", "State", "County", "Lat", "Lon",
    "Date Taken", "Date Acquired",
]


def clean(x) -> str:
    return "" if x is None else str(x).strip()


def strip_html(text) -> str:
    text = clean(text)
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text).replace("&nbsp;", " ")
    return " ".join(text.split())


def get_license_summary():
    resp = session.get(f"{BASE}/license", timeout=30)
    resp.raise_for_status()
    data = resp.json().get("data", [])
    return " | ".join(f"{r.get('licenseid','')}: {r.get('licensename','')}"
                      for r in data), data


def get_image_numbers_for_category(category_id, page_size=100, max_pages=None):
    url = f"{BASE}/image?categoryid={category_id}&pagesize={page_size}"
    nums, page = [], 0
    while url:
        page += 1
        resp = session.get(url, timeout=60)
        resp.raise_for_status()
        payload = resp.json()
        for r in payload.get("data", []):
            n = r.get("imagenumber") or r.get("imgnum")
            if n:
                nums.append(str(n))
        print(f"  list page {page:>3} | +{len(payload.get('data', [])):>4} | "
              f"total {len(nums):>5} / {payload.get('total','?')}")
        url = payload.get("nextpage") or None
        if url and max_pages is not None and page >= max_pages:
            break
        if url:
            time.sleep(0.1)
    return nums


def get_image_detail(imgnum):
    try:
        resp = session.get(f"{BASE}/image/{imgnum}", timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as e:
        print(f"  WARN: detail fetch failed for {imgnum}: {e}")
        return None


def build_image_url(detail) -> str:
    imgnum = detail.get("imgnum") or detail.get("imagenumber", "")
    try:
        max_res = int(detail.get("maxresolution", 3))
    except (TypeError, ValueError):
        max_res = 3
    path = RESOLUTION_PATH.get(max_res, "768x512")
    return f"https://bugwoodcloud.org/images/{path}/{imgnum}.jpg" if imgnum else ""


def get_orientation(detail) -> str:
    view = clean(detail.get("view") or detail.get("imageview") or "")
    if view.lower() in ("landscape", "portrait", "square"):
        return view.lower()
    try:
        w, h = int(detail.get("width", 0)), int(detail.get("height", 0))
        if w and h:
            return "landscape" if w >= h else "portrait"
    except (TypeError, ValueError):
        pass
    return ""


def parse_location(detail):
    """Split detail['location'] -> (full, country, state, county).

    Bugwood formats it as "Country, State, County" (county optional), e.g.
    "United States, Alabama, Calhoun County". Returns ("",..) when absent.
    """
    loc = detail.get("location")
    if isinstance(loc, dict):
        loc = loc.get("name") or loc.get("locationname") or ""
    full = clean(loc) or clean(detail.get("locationtext"))
    country = state = county = ""
    if full:
        parts = [p.strip() for p in full.split(",") if p.strip()]
        if len(parts) >= 1:
            country = parts[0]
        if len(parts) >= 2:
            state = parts[1]
        if len(parts) >= 3:
            county = re.sub(r"\s+County$", "", parts[2], flags=re.I).strip()
    return full, country, state, county


def _num(x):
    x = clean(x)
    try:
        v = float(x)
        return f"{v:.6f}" if v != 0 else ""
    except (TypeError, ValueError):
        return ""


def extract_row(detail, cat_id, cat_name) -> dict:
    full, country, state, county = parse_location(detail)
    return {
        "Category ID": cat_id, "Category Name": cat_name,
        "Image Number": detail.get("imgnum") or detail.get("imagenumber", ""),
        "Scientific Name": clean(detail.get("subjectscientificname")
                                 or detail.get("scientificname")),
        "Common Name": clean(detail.get("subjectname")),
        "Subject Display Name": clean(detail.get("subjectdisplayname")),
        "Host Name": clean(detail.get("hostname")),
        "Host Scientific Name": clean(detail.get("hostscientificname")),
        "Descriptor Name": clean(detail.get("descriptorname")),
        "Description": strip_html(detail.get("description")),
        "Photographer": clean(detail.get("photographer")),
        "Organization": clean(detail.get("organization")),
        "Orientation": get_orientation(detail),
        "Citation": clean(detail.get("citation")),
        "Max Resolution": detail.get("maxresolution", ""),
        "Image URL": build_image_url(detail),
        "Location": full, "Country": country, "State": state, "County": county,
        "Lat": _num(detail.get("lat")), "Lon": _num(detail.get("lon")),
        "Date Taken": clean(detail.get("datetaken")),
        "Date Acquired": clean(detail.get("dateacquired")),
    }


def scrape(max_pages=None, output="bugwood_disease_scraped.csv",
           categories=None, limit=None) -> pd.DataFrame:
    categories = categories or DISEASE_CATEGORIES
    all_rows, seen = [], set()
    fill = {"Date Taken": 0, "Date Acquired": 0, "County": 0, "Lat": 0}

    for cat_id, cat_name in categories.items():
        print(f"\n{'='*60}\nCategory {cat_id}: {cat_name}\n{'='*60}")
        try:
            img_numbers = get_image_numbers_for_category(cat_id, 100, max_pages)
        except requests.HTTPError as e:
            print(f"  SKIP list fetch — {e}")
            continue
        new_nums = [n for n in img_numbers if n not in seen]
        seen.update(new_nums)
        print(f"  {len(new_nums)} new image numbers to fetch details for")
        for i, imgnum in enumerate(new_nums, 1):
            if limit and len(all_rows) >= limit:
                break
            detail = get_image_detail(imgnum)
            if detail:
                row = extract_row(detail, cat_id, cat_name)
                for k in fill:
                    if row[k]:
                        fill[k] += 1
                all_rows.append(row)
            if i % 50 == 0:
                print(f"  detail fetches: {i}/{len(new_nums)}")
            time.sleep(SLEEP_BETWEEN_DETAIL_CALLS)
        print(f"  → running total rows: {len(all_rows)}")
        if limit and len(all_rows) >= limit:
            break

    df = pd.DataFrame(all_rows, columns=COLUMN_ORDER)
    df.to_csv(output, index=False)
    n = max(len(df), 1)
    print(f"\n✓ Saved {len(df)} rows → {output}")
    print("Geo/temporal fill rates:")
    for k, v in fill.items():
        print(f"  {k:14s}: {v}/{len(df)} ({100*v//n}%)")
    return df


def main():
    ap = argparse.ArgumentParser(description="Extended Bugwood disease scraper")
    ap.add_argument("--max-pages", type=int, default=1,
                    help="list pages per category (0 = all)")
    ap.add_argument("--output", default="bugwood_disease_scraped.csv")
    ap.add_argument("--limit", type=int, default=0,
                    help="stop after N rows (0 = unlimited); for quick tests")
    args = ap.parse_args()
    scrape(max_pages=None if args.max_pages == 0 else args.max_pages,
           output=args.output, limit=args.limit or None)


if __name__ == "__main__":
    main()
