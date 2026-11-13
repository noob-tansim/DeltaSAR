"""Google Earth Engine: 2 years of Sentinel-1 SAR + Sentinel-2 optical + DEM/HAND, without downloading TBs.

One-time setup (see README):
  1. Make a Google Cloud project and register it for Earth Engine (noncommercial).
  2. In the terminal:  earthengine authenticate
  3. Set the project id:  PowerShell: $env:EE_PROJECT="my-project-id"   bash: export EE_PROJECT=my-project-id

Run:
  python -m src.acquire.gee_layers --aoi kazipur      # downloads small GeoTIFFs for the AOI
  python -m src.acquire.gee_layers --tiles            # Bangladesh-wide XYZ tile URLs (expire, re-run before demo)

AOI outputs (cache/dem/<aoi>/, all on one 30 m UTM 45N grid):
  river_mask.tif   1 = permanent river/khal (dry-season S1 dark AND (S2 NDWI>0 OR JRC occurrence>=50))
  hand.tif         Height Above Nearest Drainage, m (MERIT Hydro, 90 m resampled)
  dem.tif          Copernicus GLO-30 elevation, m
  s1_latest_vv.tif latest Sentinel-1 VV (dB) in the last 24 days + s1_latest.json with its date
  s2_rgb.tif       Sentinel-2 dry-season cloud-free true colour (uint8 RGB)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os

import requests

from src.config import AOIS, CACHE, aoi_dir

CRS = "EPSG:32645"   # UTM 45N covers all of Bangladesh's main rivers in metres
SCALE = 30


def init():
    import ee
    project = os.getenv("EE_PROJECT")
    if not project:
        raise SystemExit("Set EE_PROJECT to your Google Cloud project id first (see docstring).")
    ee.Initialize(project=project)
    return ee


def layers(ee, region):
    today = dt.date.today()
    start = (today - dt.timedelta(days=730)).isoformat()

    s1 = (ee.ImageCollection("COPERNICUS/S1_GRD")          # already in dB in Earth Engine
          .filterBounds(region).filterDate(start, today.isoformat())
          .filter(ee.Filter.eq("instrumentMode", "IW"))
          .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
          .select("VV"))
    dry = ee.Filter.calendarRange(12, 3, "month")           # Dec-Mar, wraps around the year
    # median first, then one 30 m speckle filter (filtering every scene first exceeds the EE user memory limit)
    s1_dry = s1.filter(dry).median().focal_median(30, "circle", "meters")

    def s2_mask(img):                                       # drop clouds/shadows with SCL band
        scl = img.select("SCL")
        ok = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10))
        return img.updateMask(ok)

    s2_dry = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
              .filterBounds(region).filterDate(start, today.isoformat()).filter(dry)
              .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 40)).map(s2_mask)
              .select(["B2", "B3", "B4", "B8"]).median())          # only the bands used (memory limit)
    ndwi = s2_dry.normalizedDifference(["B3", "B8"])
    jrc = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").unmask(0)

    river = s1_dry.lt(-18).And(ndwi.gt(0).Or(jrc.gte(50))).rename("river").unmask(0).toByte()
    hand = ee.Image("MERIT/Hydro/v1_0_1").select("hnd").rename("hand")
    dem = ee.ImageCollection("COPERNICUS/DEM/GLO30").select("DEM").mosaic().rename("dem")
    rgb = s2_dry.visualize(bands=["B4", "B3", "B2"], min=0, max=2500)

    recent = s1.filterDate((today - dt.timedelta(days=24)).isoformat(), today.isoformat()).sort("system:time_start", False)
    return {"s1": s1, "s1_dry": s1_dry, "river": river, "hand": hand, "dem": dem, "rgb": rgb, "recent": recent, "ndwi": ndwi,
            "s2_dry": s2_dry}


def _download(img, region, out_path):
    url = img.getDownloadURL({"region": region, "scale": SCALE, "crs": CRS, "format": "GEO_TIFF"})
    r = requests.get(url, timeout=600)
    if not r.ok:
        raise RuntimeError(f"Earth Engine download failed for {out_path.name}: HTTP {r.status_code}: {r.text[:500]}")
    out_path.write_bytes(r.content)
    print(f"[gee] {out_path}  {len(r.content) / 1e6:.1f} MB")


def export_aoi(aoi: str):
    ee = init()
    w, s, e, n = AOIS[aoi]["bbox"]
    region = ee.Geometry.Rectangle([w, s, e, n])
    L = layers(ee, region)
    d = aoi_dir(aoi, "dem")
    # river = S1 dry-season dark AND (S2 NDWI > 0 OR JRC occurrence >= 50). The combined expression exceeds the
    # Earth Engine user memory limit, so the three parts are downloaded separately and combined here, same rule.
    import numpy as np
    import rasterio
    ee_ = ee
    jrc = ee_.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").unmask(0)
    parts = {"s1dark": L["s1_dry"].lt(-18).unmask(0).toByte(),
             "b3": L["s2_dry"].select("B3").unmask(0).toInt16(),       # NDWI computed locally: B3 and B8 medians
             "b8": L["s2_dry"].select("B8").unmask(0).toInt16(),       # separately stay under the memory limit
             "jrc50": jrc.gte(50).toByte()}
    arrs = {}
    for k, img in parts.items():
        p = d / f"_river_part_{k}.tif"
        _download(img, region, p)
        with rasterio.open(p) as s_:
            arrs[k] = s_.read(1); prof_ = s_.profile
    b3, b8 = arrs["b3"].astype("float32"), arrs["b8"].astype("float32")
    with np.errstate(invalid="ignore", divide="ignore"):
        ndwi_gt0 = ((b3 - b8) / (b3 + b8)) > 0
    river = (arrs["s1dark"] == 1) & (ndwi_gt0 | (arrs["jrc50"] == 1))
    prof_.update(dtype="uint8", count=1, nodata=None, compress="deflate")
    with rasterio.open(d / "river_mask.tif", "w", **prof_) as dst:
        dst.write(river.astype("uint8"), 1)
    print(f"[gee] {d / 'river_mask.tif'}  river {river.sum() * 9e-4:.1f} km2 (30 m px)")
    _download(L["hand"].toFloat(), region, d / "hand.tif")
    _download(L["dem"].toFloat(), region, d / "dem.tif")
    _download(L["rgb"], region, d / "s2_rgb.tif")

    n_recent = L["recent"].size().getInfo()
    if n_recent:
        latest = ee.Image(L["recent"].first())
        when = ee.Date(latest.get("system:time_start")).format("YYYY-MM-dd").getInfo()
        _download(latest.focal_median(30, "circle", "meters").toFloat(), region, d / "s1_latest_vv.tif")
        (d / "s1_latest.json").write_text(json.dumps({"date": when, "sensor": "Sentinel-1 GRD VV (dB)"}))
        print(f"[gee] latest Sentinel-1 pass over {aoi}: {when}")
    else:
        print("[gee] no Sentinel-1 pass in the last 24 days")


def bangladesh_tiles():
    ee = init()
    bd = ee.FeatureCollection("USDOS/LSIB_SIMPLE/2017").filter(ee.Filter.eq("country_na", "Bangladesh"))
    L = layers(ee, bd.geometry())
    def url(img, vis):
        return img.clip(bd).getMapId(vis)["tile_fetcher"].url_format
    tiles = {
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
        "note": "Earth Engine tile URLs expire; re-run --tiles on demo morning. Offline fallback = outputs/<aoi>/overlays.",
        "river_khal": url(L["river"].selfMask(), {"palette": ["0055ff"]}),
        "hand_m": url(L["hand"], {"min": 0, "max": 15, "palette": ["d73027", "fc8d59", "fee08b", "d9ef8b", "1a9850"]}),
        "s2_truecolor_dry": url(L["rgb"], {}),
        "s1_dry_vv_db": url(L["s1_dry"], {"min": -25, "max": 0}),
    }
    (CACHE / "map_tiles.json").write_text(json.dumps(tiles, indent=1))
    print(json.dumps(tiles, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--aoi", default=None)
    ap.add_argument("--tiles", action="store_true")
    a = ap.parse_args()
    if a.tiles:
        bangladesh_tiles()
    if a.aoi or not a.tiles:
        export_aoi(a.aoi or "kazipur")
