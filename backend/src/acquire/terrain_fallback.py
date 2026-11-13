"""Terrain fallback when Earth Engine is not set up yet. Deterministic, no model, no login.

  python -m src.acquire.terrain_fallback --aoi kazipur

Writes the three files run_aoi needs, on the analysis grid (config.base_profile: EPSG:32645, 20 m):
  cache/dem/<aoi>/river_mask.tif  uint8 1 = persistent water: HH below the water threshold in EVERY
                                  available 069A NISAR pass (Otsu on the earliest pass), specks < 2 ha removed
  cache/dem/<aoi>/dem.tif         Copernicus GLO-30 (public AWS bucket, EGM2008), bilinear to the grid
  cache/dem/<aoi>/hand.tif        approx. height above river = DEM - DEM of the nearest river_mask pixel, >= 0
  cache/dem/<aoi>/terrain_receipt.json  provenance; run_aoi carries its label into summary.json

This is NOT MERIT Hydro HAND and NOT the Earth Engine river mask. It never overwrites files written by
gee_layers.py (it refuses if they exist without a fallback receipt).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math

import numpy as np
import rasterio
import requests
from rasterio.warp import Resampling, reproject, transform_bounds
from scipy import ndimage

from src.compute import water as wt
from src.config import CACHE, WATER_SPECK_HA, aoi_dir, base_profile

LABEL = "FALLBACK: SAR persistent water + GLO-30 nearest-river height (not MERIT Hydro HAND)"
TRACK = "069A"

GLO30_URL = ("https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_{ns}{lat:02d}_00_{ew}{lon:03d}_00_DEM/"
             "Copernicus_DSM_COG_10_{ns}{lat:02d}_00_{ew}{lon:03d}_00_DEM.tif")


def _write(path, arr, prof, dtype, nodata):
    p = dict(prof, count=1, dtype=dtype, nodata=nodata, compress="deflate", tiled=True)
    with rasterio.open(path, "w", **p) as d:
        d.write(arr.astype(dtype), 1)


def _to_grid(src_path, prof, resampling):
    dst = np.full((prof["height"], prof["width"]), np.nan, dtype="float32")
    with rasterio.open(src_path) as s:
        reproject(rasterio.band(s, 1), dst, dst_transform=prof["transform"], dst_crs=prof["crs"],
                  resampling=resampling, dst_nodata=np.nan)
    return dst


def persistent_water(aoi, prof):
    from src.pipeline.run_aoi import list_passes   # same pass discovery as the pipeline
    passes = [p for p in list_passes(aoi) if p["track"] == TRACK]
    if not passes:
        raise SystemExit(f"No {TRACK} NISAR passes in cache/sar/{aoi}; run nisar_subset cut first")
    px = prof["transform"].a
    first = _to_grid(passes[0]["hh_path"], prof, Resampling.average)
    # same function the pipeline uses for T_HH (src/compute/water.py), on the same baseline scene and grid
    thr, method = wt.valley_threshold(first) or (round(wt.otsu_threshold(first), 2), "Otsu -30..0 dB (no clear valley)")
    print(f"[terrain] threshold {thr} dB on {passes[0]['date']}: {method}")
    water = None
    for p in passes:
        hh = first if p is passes[0] else _to_grid(p["hh_path"], prof, Resampling.average)
        w = wt.classify(hh, None, thr, px)["open_water"]          # NaN (unknown) counts as not water
        water = w if water is None else (water & w)
        print(f"[terrain] {p['date']} {TRACK}: water {w.sum() * px * px / 1e6:.1f} km2, persistent so far "
              f"{water.sum() * px * px / 1e6:.1f} km2")
    water = wt.remove_small(water, int(math.ceil(WATER_SPECK_HA * 1e4 / px ** 2)))
    return water, thr, f"{method}, on {passes[0]['date']} HH", [p["date"] for p in passes]


def glo30(prof):
    raw = CACHE / "dem" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    w, s, e, n = transform_bounds(prof["crs"], "EPSG:4326", *rasterio.transform.array_bounds(
        prof["height"], prof["width"], prof["transform"]))
    dem = np.full((prof["height"], prof["width"]), np.nan, dtype="float32")
    urls = []
    for lat in range(math.floor(s), math.floor(n) + 1):
        for lon in range(math.floor(w), math.floor(e) + 1):
            url = GLO30_URL.format(ns="N" if lat >= 0 else "S", lat=abs(lat), ew="E" if lon >= 0 else "W", lon=abs(lon))
            path = raw / url.rsplit("/", 1)[1]
            if not path.exists():
                r = requests.get(url, timeout=600)
                if r.status_code == 404:
                    print(f"[terrain] no GLO-30 tile (ocean?): {url}")
                    continue
                r.raise_for_status()
                path.write_bytes(r.content)
                print(f"[terrain] downloaded {path.name} {len(r.content) / 1e6:.1f} MB")
            part = _to_grid(path, prof, Resampling.bilinear)
            dem = np.where(np.isfinite(dem), dem, part)
            urls.append(url)
    if not urls:
        raise SystemExit("No GLO-30 tiles could be fetched for the AOI")
    return dem, urls


def nearest_river_height(dem, river, px):
    if not river.any():
        raise SystemExit("river_mask is empty; cannot compute height above river")
    _, (ri, ci) = ndimage.distance_transform_edt(~river, return_indices=True)
    ref = dem[ri, ci]
    # a river pixel without DEM: fall back to the median DEM over the river
    ref = np.where(np.isfinite(ref), ref, np.nanmedian(dem[river]))
    hand = np.clip(dem - ref, 0, None).astype("float32")
    hand[river] = 0.0
    return hand


def run(aoi: str) -> dict:
    prof = base_profile(aoi)
    d = aoi_dir(aoi, "dem")
    rc_path = d / "terrain_receipt.json"
    existing = [f for f in ("river_mask.tif", "hand.tif", "dem.tif") if (d / f).exists()]
    if existing and not rc_path.exists():
        raise SystemExit(f"{existing} already exist without a fallback receipt (Earth Engine layers?); not overwriting")
    px = prof["transform"].a
    river, thr, thr_method, dates = persistent_water(aoi, prof)
    dem, urls = glo30(prof)
    hand = nearest_river_height(dem, river, px)
    _write(d / "river_mask.tif", river.astype("uint8"), prof, "uint8", 255)
    _write(d / "dem.tif", dem, prof, "float32", np.nan)
    _write(d / "hand.tif", hand, prof, "float32", np.nan)
    land = ~river & np.isfinite(hand)
    receipt = {
        "source": LABEL,
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
        "grid": {"crs": prof["crs"], "pixel_m": px, "width": prof["width"], "height": prof["height"]},
        "river_mask": {"method": f"HH < threshold in every {TRACK} pass (3x3 median, >= 2000 m2 per pass), "
                                 f"then components < {WATER_SPECK_HA} ha removed; unknown pixels = not water",
                       "track": TRACK, "dates_used": dates, "threshold_db": thr,
                       "threshold_method": thr_method,
                       "area_km2": round(float(river.sum()) * px * px / 1e6, 2)},
        "dem": {"source": "Copernicus GLO-30 DSM (EGM2008 geoid), public AWS bucket", "urls": urls,
                "resampling": "bilinear"},
        "hand": {"method": "DEM minus DEM at the nearest river_mask pixel (Euclidean), clipped at 0; river = 0",
                 "median_land_m": round(float(np.nanmedian(hand[land])), 2) if land.any() else None,
                 "p90_land_m": round(float(np.nanpercentile(hand[land], 90)), 2) if land.any() else None},
    }
    rc_path.write_text(json.dumps(receipt, indent=1))
    print(f"[terrain] river {receipt['river_mask']['area_km2']} km2 (T = {thr} dB), HAND land median "
          f"{receipt['hand']['median_land_m']} m, p90 {receipt['hand']['p90_land_m']} m -> {d}")
    return receipt


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--aoi", default="kazipur")
    run(ap.parse_args().aoi)
