"""Cloud-free Sentinel-2 true colour per radar date, from Earth Engine, with a RULE-BASED cloud mask (no ML products).

  python -m src.acquire.gee_optical --aoi kazipur            # every observed radar date
  python -m src.acquire.gee_optical --aoi kazipur --dates 20261004

For each target (radar) date:
  * Sentinel-2 L2A (COPERNICUS/S2_SR_HARMONIZED) within +/- WINDOW days (widened to WINDOW_WIDE if too much is unfilled)
  * per scene, a pixel is cloudy if: SCL in {3 shadow, 8 cloud medium, 9 cloud high, 10 cirrus, 11 snow}
    OR QA60 bit 10/11 set OR blue (B2) reflectance > 0.20 (thick haze/cloud) OR NDSI > 0.4 with B2 > 0.10
  * every pixel takes the clear observation NEAREST IN TIME to the target date (qualityMosaic on -|days|)
  * outputs: s2cf_<date>_rgb.tif (uint8 RGB, B4/B3/B2 stretched 0..2500), s2cf_<date>_days.tif (|days| from target,
    255 = unfilled), receipt with scene ids/dates, median offset and unfilled fraction.
Optional (--mask csplus): Cloud Score Plus (cs_cdf >= 0.6) instead of the rule-based mask; labelled as such.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json

import numpy as np
import rasterio
import requests

from src.acquire.gee_layers import init
from src.config import AOIS, CACHE, CRS

SCALE = 20
WINDOW, WINDOW_WIDE = 20, 45
MAX_UNFILLED_PCT = 5.0
MAX_SCENES = 24          # nearest scenes in time per composite (Earth Engine user memory limit)


def _dates(aoi):
    from src.pipeline.run_aoi import list_passes
    return sorted({p["date"] for p in list_passes(aoi)})


def composite(ee, region, target: str, window: int, mask: str):
    t = ee.Date(f"{target[:4]}-{target[4:6]}-{target[6:]}")
    col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(region)
           .filterDate(t.advance(-window, "day"), t.advance(window + 1, "day"))
           .select(["B2", "B3", "B4", "B11", "SCL", "QA60"])
           .map(lambda i: i.clip(region).set("absdays", ee.Number(i.date().difference(t, "day")).abs()))
           .sort("absdays").limit(MAX_SCENES))                   # needed bands, AOI only, nearest scenes (memory limit)
    if mask == "csplus":
        cs = ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED")
        col = col.linkCollection(cs, ["cs_cdf"])

    def prep(img):
        if mask == "csplus":
            clear = img.select("cs_cdf").gte(0.6)
        else:
            scl = img.select("SCL"); qa = img.select("QA60")
            b2 = img.select("B2").divide(10000); b3 = img.select("B3"); b11 = img.select("B11")
            ndsi = b3.subtract(b11).divide(b3.add(b11))
            cloudy = (scl.eq(3).Or(scl.eq(8)).Or(scl.eq(9)).Or(scl.eq(10)).Or(scl.eq(11))
                      .Or(qa.bitwiseAnd(1 << 10).neq(0)).Or(qa.bitwiseAnd(1 << 11).neq(0))
                      .Or(b2.gt(0.20)).Or(ndsi.gt(0.4).And(b2.gt(0.10))))
            clear = cloudy.Not()
        days = ee.Number(img.date().difference(t, "day")).abs()
        q = ee.Image.constant(days).multiply(-1).rename("q").float()
        d = ee.Image.constant(days).rename("days").toFloat()
        return img.select(["B4", "B3", "B2"]).addBands(d).addBands(q).updateMask(clear)

    mosaic = col.map(prep).qualityMosaic("q")
    meta = col.aggregate_array("system:index"), col.aggregate_array("system:time_start")
    return mosaic, meta


def _get(img, region, path, scale=SCALE):
    url = img.getDownloadURL({"region": region, "scale": scale, "crs": CRS, "format": "GEO_TIFF"})
    r = requests.get(url, timeout=600)
    if not r.ok:
        raise RuntimeError(f"Earth Engine download failed for {path.name}: HTTP {r.status_code}: {r.text[:400]}")
    path.write_bytes(r.content)
    return len(r.content)


def run(aoi="kazipur", dates=None, mask="rules"):
    ee = init()
    w, s, e, n = AOIS[aoi]["bbox"]
    region = ee.Geometry.Rectangle([w, s, e, n])
    od = CACHE / "optical" / aoi; od.mkdir(parents=True, exist_ok=True)
    results = []
    for d in dates or _dates(aoi):
        if (od / f"s2cf_{d}_receipt.json").exists() and not dates:
            results.append(json.loads((od / f"s2cf_{d}_receipt.json").read_text())); continue
        try:
            results.append(_one(ee, region, od, d, mask))
        except Exception as exc:
            print(f"[optical] {d}: FAILED {exc!r}"[:400])
    return results


def _one(ee, region, od, d, mask):
    if True:
        for window in (WINDOW, WINDOW_WIDE):
            mos, (ids, times) = composite(ee, region, d, window, mask)
            rgb = mos.select(["B4", "B3", "B2"]).visualize(min=0, max=2500)
            days = mos.select("days").unmask(255).clamp(0, 255).toByte()
            p_rgb, p_days = od / f"s2cf_{d}_rgb.tif", od / f"s2cf_{d}_days.tif"
            _get(rgb, region, p_rgb); _get(days, region, p_days)
            with rasterio.open(p_days) as src:
                dd = src.read(1)
            filled = dd < 255
            unfilled = round(100 * (1 - filled.mean()), 1)
            med = float(np.median(dd[filled])) if filled.any() else None
            if unfilled <= MAX_UNFILLED_PCT or window == WINDOW_WIDE:
                break
        ids = ids.getInfo(); times = times.getInfo()
        scenes = sorted({(i, dt.datetime.utcfromtimestamp(t / 1000).strftime("%Y-%m-%d")) for i, t in zip(ids, times)},
                        key=lambda x: x[1])
        rc = {"target_date": d, "window_days": window, "mask": "rule-based (SCL 3/8/9/10/11 + QA60 + blue>0.20 + NDSI)"
              if mask == "rules" else "Cloud Score Plus cs_cdf >= 0.6",
              "method": "per pixel, the clear observation nearest in time to the target date (qualityMosaic on -|days|)",
              "median_offset_days": med, "unfilled_pct": unfilled, "n_scenes": len(scenes),
              "scenes": [{"id": i, "date": t} for i, t in scenes], "scale_m": SCALE, "stretch": "B4/B3/B2 0..2500 -> 0..255",
              "source": "Copernicus Sentinel-2 L2A via Google Earth Engine (COPERNICUS/S2_SR_HARMONIZED)",
              "rgb": p_rgb.name, "days": p_days.name}
        (od / f"s2cf_{d}_receipt.json").write_text(json.dumps(rc, indent=1))
        print(f"[optical] {d}: window +/-{window} d, median offset {med} d, unfilled {unfilled}%, {len(scenes)} scenes")
        return rc


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--aoi", default="kazipur"); ap.add_argument("--dates", nargs="*")
    ap.add_argument("--mask", choices=["rules", "csplus"], default="rules")
    a = ap.parse_args()
    run(a.aoi, a.dates, a.mask)
