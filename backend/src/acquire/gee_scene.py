"""One whole, clear optical scene per radar date (no pixel patchwork), from Earth Engine.

  python -m src.acquire.gee_scene --aoi kazipur

For every observed radar date:
  * candidate days = Sentinel-2 L2A days (same-day tiles mosaicked) and Landsat 8/9 C2 L2 days within +/-SEARCH_DAYS
  * per day: cloud % computed over the AOI itself (S2: SCL 3/8/9/10; Landsat: QA_PIXEL cloud, shadow, cirrus bits)
    and AOI coverage % (pixels with data)
  * a day qualifies if AOI cloud < MAX_CLOUD and coverage >= MIN_COVER; the qualifying day nearest the radar date
    wins (Sentinel-2 preferred on ties); days are never mixed
  * export: true colour at 10 m (S2) / 30 m (Landsat), ONE fixed stretch for all dates (reflectance 0..0.30, gamma 1.3),
    nothing masked inside the scene, clipped exactly to the AOI rectangle (Esri continues outside)
Outputs cache/optical/<aoi>/scene_<sensor>_<day>_rgb.tif (shared when several radar dates pick the same day) and
scene_for_<radar date>.json (scene ids, actual date, days from the radar date, AOI cloud %, label).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json

import numpy as np
import rasterio
import requests
from rasterio.merge import merge

from src.acquire.gee_layers import init
from src.config import AOIS, CACHE, CRS

SEARCH_DAYS = 150
MAX_CLOUD = 15.0
MIN_COVER = 95.0
STRETCH = (0.0, 0.30, 1.3)          # reflectance min, max, gamma: identical for every date and sensor
EVAL_SCALE = 120                     # metres, for the cloud / coverage statistics


def _d(s):
    return dt.date(int(s[:4]), int(s[4:6]), int(s[6:]))


def _radar_dates(aoi):
    from src.pipeline.run_aoi import list_passes
    return sorted({p["date"] for p in list_passes(aoi) if p["track"] == "069A"})


def candidates(ee, region, start, end):
    """[(day, sensor, cloud%, cover%, [ids])] for every S2 and Landsat day in [start, end]."""
    s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(region).filterDate(start, end)
          .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 70)))
    ls = (ee.ImageCollection("LANDSAT/LC08/C02/T1_L2").merge(ee.ImageCollection("LANDSAT/LC09/C02/T1_L2"))
          .filterBounds(region).filterDate(start, end).filter(ee.Filter.lt("CLOUD_COVER", 70)))

    def day_stats(col, sensor):
        days = col.aggregate_array("system:time_start").map(lambda t: ee.Date(t).format("YYYYMMdd")).distinct()

        def one(day):
            d0 = ee.Date.parse("YYYYMMdd", day)
            imgs = col.filterDate(d0, d0.advance(1, "day"))
            if sensor == "S2":
                scl = imgs.select("SCL").mosaic()
                cloud = scl.eq(3).Or(scl.eq(8)).Or(scl.eq(9)).Or(scl.eq(10))
                valid = scl.gt(0)
            else:
                qa = imgs.select("QA_PIXEL").mosaic()
                cloud = (qa.bitwiseAnd(1 << 3).neq(0).Or(qa.bitwiseAnd(1 << 4).neq(0))
                         .Or(qa.bitwiseAnd(1 << 2).neq(0)).Or(qa.bitwiseAnd(1 << 1).neq(0)))
                valid = qa.bitwiseAnd(1).eq(0)
            st = ee.Image.cat(cloud.And(valid).rename("c"), valid.rename("v"), ee.Image.constant(1).rename("a")) \
                .unmask(0).reduceRegion(ee.Reducer.sum(), region, EVAL_SCALE, maxPixels=1e9)
            return ee.Feature(None, {"day": day, "c": st.get("c"), "v": st.get("v"), "a": st.get("a"),
                                     "ids": imgs.aggregate_array("system:index")})
        return ee.FeatureCollection(days.map(one)).getInfo()["features"]

    out = []
    for sensor, col in (("S2", s2), ("L89", ls)):
        for f in day_stats(col, sensor):
            p = f["properties"]
            a = max(p["a"] or 1, 1)
            v = p["v"] or 0
            out.append((p["day"], sensor, round(100 * (p["c"] or 0) / max(v, 1), 1), round(100 * v / a, 1), p["ids"]))
    return out


def rgb_image(ee, region, day, sensor):
    d0 = ee.Date.parse("YYYYMMdd", day)
    lo, hi, gamma = STRETCH
    if sensor == "S2":
        img = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(region).filterDate(d0, d0.advance(1, "day"))
               .mosaic().select(["B4", "B3", "B2"]).divide(10000))
        scale = 10
    else:
        col = (ee.ImageCollection("LANDSAT/LC08/C02/T1_L2").merge(ee.ImageCollection("LANDSAT/LC09/C02/T1_L2"))
               .filterBounds(region).filterDate(d0, d0.advance(1, "day")))
        img = col.mosaic().select(["SR_B4", "SR_B3", "SR_B2"]).multiply(0.0000275).add(-0.2)
        scale = 30
    return img.visualize(min=lo, max=hi, gamma=gamma), scale


def export(ee, aoi, day, sensor, out_path):
    """Download in 2x2 tiles (EE request size limit) on the exact analysis grid extent, then merge."""
    xmin, ymin, xmax, ymax = AOIS[aoi]["utm_extent"]
    w, s, e, n = AOIS[aoi]["bbox"]
    region = ee.Geometry.Rectangle([w, s, e, n])
    vis, scale = rgb_image(ee, region, day, sensor)
    parts = []
    xs, ys = np.linspace(xmin, xmax, 3), np.linspace(ymin, ymax, 3)
    for i in range(2):
        for j in range(2):
            rect = ee.Geometry.Rectangle([xs[i], ys[j], xs[i + 1], ys[j + 1]], CRS, False)
            for attempt in range(4):                  # Earth Engine downloads sometimes time out: retry
                try:
                    url = vis.getDownloadURL({"region": rect, "scale": scale, "crs": CRS, "format": "GEO_TIFF"})
                    r = requests.get(url, timeout=900)
                    if r.ok:
                        break
                    err = f"HTTP {r.status_code}: {r.text[:300]}"
                except requests.RequestException as exc:
                    err = repr(exc)
            else:
                raise RuntimeError(f"EE download failed after retries: {err}")
            p = out_path.with_name(out_path.stem + f"_part{i}{j}.tif"); p.write_bytes(r.content); parts.append(p)
    srcs = [rasterio.open(p) for p in parts]
    mosaic, tr = merge(srcs, bounds=(xmin, ymin, xmax, ymax), res=scale)
    prof = srcs[0].profile; [s_.close() for s_ in srcs]
    prof.update(height=mosaic.shape[1], width=mosaic.shape[2], transform=tr, compress="deflate", tiled=True, count=3)
    with rasterio.open(out_path, "w", **prof) as dst:
        dst.write(mosaic[:3])
    for p in parts:
        p.unlink()


def run(aoi="kazipur", dates=None):
    ee = init()
    w, s, e, n = AOIS[aoi]["bbox"]
    region = ee.Geometry.Rectangle([w, s, e, n])
    od = CACHE / "optical" / aoi; od.mkdir(parents=True, exist_ok=True)
    rdates = dates or _radar_dates(aoi)
    start = (_d(min(rdates)) - dt.timedelta(days=SEARCH_DAYS)).isoformat()
    end = min(_d(max(rdates)) + dt.timedelta(days=SEARCH_DAYS), dt.date.today()).isoformat()
    cpath = od / "scene_candidates.json"
    if cpath.exists() and dt.datetime.fromtimestamp(cpath.stat().st_mtime).date() == dt.date.today():
        cands = [tuple(c) for c in json.loads(cpath.read_text())]       # reuse today's search (it takes ~15 min)
    else:
        cands = candidates(ee, region, start, end)
        cpath.write_text(json.dumps(cands, indent=0))
    print(f"[scene] {len(cands)} candidate days ({sum(c[1] == 'S2' for c in cands)} S2, {sum(c[1] == 'L89' for c in cands)} Landsat)")
    ok = [c for c in cands if c[2] < MAX_CLOUD and c[3] >= MIN_COVER]
    table = []
    for rd in rdates:
        if not ok:
            rec = {"radar_date": rd, "status": "none", "label": "No clear optical image this season; showing the sharp satellite base map"}
        else:
            best = min(ok, key=lambda c: (abs((_d(c[0]) - _d(rd)).days), c[1] != "S2"))
            off = (_d(best[0]) - _d(rd)).days
            day_s = _d(best[0]).strftime("%-d %b %Y") if False else f"{_d(best[0]).day} {_d(best[0]).strftime('%b %Y')}"
            when = f"{abs(off)} days {'after' if off > 0 else 'before'} this radar date" if off else "same day as this radar date"
            label = f"Optical image from {day_s} ({'Sentinel-2' if best[1] == 'S2' else 'Landsat 8/9'}, {best[2]}% cloud over the area), {when}"
            if abs(off) > 30:
                label += "; no clear image exists nearer because of monsoon cloud"
            tif = od / f"scene_{best[1]}_{best[0]}_rgb.tif"
            if not tif.exists():
                export(ee, aoi, best[0], best[1], tif)
                print(f"[scene] exported {tif.name}")
            rec = {"radar_date": rd, "status": "ok", "day": best[0], "sensor": best[1], "days_offset": off,
                   "aoi_cloud_pct": best[2], "aoi_cover_pct": best[3], "scene_ids": best[4], "rgb": tif.name,
                   "stretch": {"reflectance_min": STRETCH[0], "reflectance_max": STRETCH[1], "gamma": STRETCH[2]},
                   "rule": f"nearest single day with AOI cloud < {MAX_CLOUD}% (SCL / QA_PIXEL over the AOI) and coverage >= {MIN_COVER}%",
                   "label": label}
        (od / f"scene_for_{rd}.json").write_text(json.dumps(rec, indent=1))
        table.append(rec)
        print(f"[scene] {rd}: {rec['label']}")
    return table


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--aoi", default="kazipur"); ap.add_argument("--dates", nargs="*")
    a = ap.parse_args()
    run(a.aoi, a.dates)
