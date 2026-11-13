"""End-to-end run for the AOI: layers -> threshold -> same-track pairs -> 7-day layer -> static files.

  python -m src.pipeline.run_aoi                    # pairs, overlays, union + location JSON
  python -m src.pipeline.run_aoi --calibrate        # also recalibrate on the newest full-track pass
  python -m src.pipeline.run_aoi --replay           # season replay: calibrate pass by pass, Jun -> Oct

Inputs:
  cache/dem/<aoi>/river_mask.tif, hand.tif, dem.tif, s2_rgb.tif  <- gee_layers.py
  cache/dem/<aoi>/nisar_watermask.tif (optional, ASF NISAR_WATERMASK N24-25 E89-90)
  cache/sar/<aoi>/nisar_<date>_<track>_{HHHH,HVHV}_db.tif + _receipt.json  <- nisar_subset.py
  cache/vector/unions.geojson (optional, geoBoundaries ADM4 clipped to the AOI)
Outputs (static, Plan B ready) in outputs/<aoi>/:
  summary.json, union_summary.json, overlays.json + overlays/*.png, river_khal.geojson,
  pairs/<pair>.json, layers/*.tif (point queries)
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import re
import warnings

import numpy as np
import rasterio
import rasterio.errors
from rasterio import features
from rasterio.warp import Resampling, calculate_default_transform, reproject, transform as warp_xy, transform_geom
from scipy import ndimage

from src.acquire.weather import get_rain, observed_rain
from src.compute import exposure
from src.compute import flood_prob as fp
from src.compute import water as wt
from src.config import AOIS, FULL_TRACKS, NISAR_GAP_UTC, PAIRS, VECTOR, aoi_dir, base_profile, out_dir

warnings.filterwarnings("ignore", category=rasterio.errors.NotGeoreferencedWarning)
CODE_VERSION = "deltasar-sar-dem 0.2"


# ---------------------------------------------------------------- raster helpers
def to_grid(path, prof, resampling=Resampling.average, band=1):
    dst = np.full((prof["height"], prof["width"]), np.nan, dtype="float32")
    with rasterio.open(path) as s:
        reproject(rasterio.band(s, band), dst, dst_transform=prof["transform"], dst_crs=prof["crs"],
                  resampling=resampling, dst_nodata=np.nan)
    return dst


def write_tif(path, arr, prof, dtype="float32", nodata=np.nan):
    p = dict(prof, count=1, dtype=dtype, nodata=nodata, compress="deflate", tiled=True)
    with rasterio.open(path, "w", **p) as d:
        d.write(arr.astype(dtype), 1)


def colorize(arr, vmin, vmax, stops, alpha_mask=None):
    cols = np.array([[int(h[i:i + 2], 16) for i in (0, 2, 4)] for h in stops], float)
    t = np.clip((arr - vmin) / (vmax - vmin), 0, 1)
    pos = np.nan_to_num(t, nan=0) * (len(stops) - 1)
    i0 = np.floor(pos).astype(int).clip(0, len(stops) - 2); f = (pos - i0)[..., None]
    rgb = cols[i0] * (1 - f) + cols[i0 + 1] * f
    a = np.where(np.isfinite(arr), 255, 0)
    if alpha_mask is not None:
        a = np.where(alpha_mask, a, 0)
    return np.dstack([rgb, a]).astype("uint8")


def mask_rgba(mask, hexcol):
    return colorize(mask.astype(float), 0, 1, [hexcol, hexcol], mask)


def grey_rgba(hh):
    g = np.clip((np.nan_to_num(hh, nan=-25) + 25) / 25 * 255, 0, 255)
    return np.dstack([g, g, g, np.where(np.isfinite(hh), 255, 0)]).astype("uint8")


def two_rgba(mask1, hex1, mask2, hex2):
    """Two disjoint masks in one overlay (mask1 wins where both)."""
    out = mask_rgba(mask2, hex2)
    a = mask_rgba(mask1, hex1)
    return np.where(mask1[..., None], a, out)


def sar_rgb(hh, hv):
    """GIBS-style false colour: R = HH, G = HV, B = HH. Water black, vegetation green, double bounce magenta."""
    sc = lambda v, lo, hi: np.clip((np.nan_to_num(v, nan=lo) - lo) / (hi - lo) * 255, 0, 255)  # noqa: E731
    r = sc(hh, -25, 0); g = sc(hv if hv is not None else hh, -30, -5)
    return np.dstack([r, g, r, np.where(np.isfinite(hh), 255, 0)]).astype("uint8")


def write_png_4326(path, rgba, prof):
    h, w = rgba.shape[:2]
    left, top = prof["transform"] * (0, 0); right, bottom = prof["transform"] * (w, h)
    tr, W, H = calculate_default_transform(prof["crs"], "EPSG:4326", w, h, left, bottom, right, top)
    out = np.zeros((4, H, W), dtype="uint8")
    for b in range(4):
        reproject(rgba[..., b], out[b], src_transform=prof["transform"], src_crs=prof["crs"],
                  dst_transform=tr, dst_crs="EPSG:4326", resampling=Resampling.nearest)
    with rasterio.open(path, "w", driver="PNG", width=W, height=H, count=4, dtype="uint8") as d:
        d.write(out)
    west, north = tr * (0, 0); east, south = tr * (W, H)
    return [round(west, 6), round(south, 6), round(east, 6), round(north, 6)]


def write_webp_4326(path, rgba, prof, quality=82):
    """Like write_png_4326 but lossy WebP (photos: ~10x smaller than PNG at 10 m). GDAL WEBP is CreateCopy-only."""
    from rasterio.io import MemoryFile
    from rasterio.shutil import copy as rcopy
    h, w = rgba.shape[:2]
    left, top = prof["transform"] * (0, 0); right, bottom = prof["transform"] * (w, h)
    tr, W, H = calculate_default_transform(prof["crs"], "EPSG:4326", w, h, left, bottom, right, top)
    out = np.zeros((4, H, W), dtype="uint8")
    for b in range(4):
        reproject(rgba[..., b], out[b], src_transform=prof["transform"], src_crs=prof["crs"],
                  dst_transform=tr, dst_crs="EPSG:4326", resampling=Resampling.bilinear if b < 3 else Resampling.nearest)
    with MemoryFile() as mf:
        with mf.open(driver="GTiff", width=W, height=H, count=4, dtype="uint8") as d:
            d.write(out)
        with mf.open() as src:
            rcopy(src, str(path), driver="WEBP", QUALITY=quality)
    west, north = tr * (0, 0); east, south = tr * (W, H)
    return [round(west, 6), round(south, 6), round(east, 6), round(north, 6)]


# ---------------------------------------------------------------- SAR passes
def list_passes(aoi):
    out = []
    for f in sorted(glob.glob(str(aoi_dir(aoi, "sar") / "nisar_*_HHHH_db.tif"))):
        m = re.search(r"nisar_(\d{8})_(\d{3}[AD])_HHHH", f)
        if not m:
            continue
        rc = f.replace("_HHHH_db.tif", "_receipt.json")
        receipt = json.load(open(rc)) if glob.glob(rc) else {}
        out.append({"date": m.group(1), "track": m.group(2), "hh_path": f, "receipt": receipt})
    return sorted(out, key=lambda p: p["date"])


def _grid_cached(path, prof):
    """to_grid with a .npy cache next to the cut (keyed by the tif's mtime and the grid size)."""
    import os
    cache = path.replace(".tif", f"_grid{prof['transform'].a:.0f}m.npy")
    mt = os.path.getmtime(path)
    if os.path.exists(cache) and os.path.getmtime(cache) >= mt:
        a = np.load(cache)
        if a.shape == (prof["height"], prof["width"]):
            return a
    a = to_grid(path, prof)
    np.save(cache, a)
    return a


def load_pass(p, prof):
    hv_path = p["hh_path"].replace("_HHHH_", "_HVHV_")
    return {"hh": _grid_cached(p["hh_path"], prof), "hv": _grid_cached(hv_path, prof) if glob.glob(hv_path) else None}


def in_gap(date):
    d = dt.datetime.strptime(date, "%Y%m%d").date()
    g0, g1 = (dt.date.fromisoformat(x[:10]) for x in NISAR_GAP_UTC)
    return g0 <= d <= g1


# ---------------------------------------------------------------- main
def run(aoi="kazipur", calibrate=False, replay=False) -> dict:
    cfg = AOIS[aoi]; prof = base_profile(aoi); px = cfg["grid_m"]
    w, s, e, n = cfg["bbox"]; lat, lon = (s + n) / 2, (w + e) / 2
    dem_dir, od = aoi_dir(aoi, "dem"), out_dir(aoi)
    (od / "pairs").mkdir(exist_ok=True)

    # --- terrain + permanent channel
    hand = to_grid(dem_dir / "hand.tif", prof, Resampling.bilinear)
    dem = to_grid(dem_dir / "dem.tif", prof, Resampling.bilinear) if (dem_dir / "dem.tif").exists() else None
    river = to_grid(dem_dir / "river_mask.tif", prof, Resampling.nearest) >= 0.5
    sources = {"river_khal": "Sentinel-1 2-yr dry season + Sentinel-2 NDWI + JRC GSW (Earth Engine)",
               "hand": "MERIT Hydro HAND", "dem": "Copernicus GLO-30 (EGM2008 geoid)"}
    terrain_rc = dem_dir / "terrain_receipt.json"      # written only by src/acquire/terrain_fallback.py
    if terrain_rc.exists():
        trc = json.loads(terrain_rc.read_text())
        sources.update({"river_khal": f"{trc['source']} | {trc['river_mask']['method']}, {trc['river_mask']['track']} "
                                      f"{', '.join(trc['river_mask']['dates_used'])}, T = {trc['river_mask']['threshold_db']} dB",
                        "hand": f"{trc['source']} | {trc['hand']['method']}",
                        "terrain_fallback": True, "terrain_receipt": trc})
    if (dem_dir / "nisar_watermask.tif").exists():
        river |= to_grid(dem_dir / "nisar_watermask.tif", prof, Resampling.nearest) >= 0.5
        sources["river_khal"] += " + NISAR_WATERMASK v0.5"
    dist_river = (ndimage.distance_transform_edt(~river) * px).astype("float32")
    stable_land = (dist_river > 2000) & (np.nan_to_num(hand, nan=0) > 5)

    passes = [p for p in list_passes(aoi) if p["track"] in FULL_TRACKS]
    by_key = {(p["track"], p["date"]): p for p in passes}

    # --- one T_HH per track, from that track's earliest pass (its baseline), reused for all its dates
    thr_by_track = {}
    for tr in sorted({p["track"] for p in passes}):
        bp = next(p for p in passes if p["track"] == tr)
        t = wt.reach_threshold(load_pass(bp, prof)["hh"], river, stable_land, near_river=dist_river <= 2000)
        t["baseline_pass"] = f"{bp['date']} {tr}"
        thr_by_track[tr] = t
        print(f"[thr] {tr}: T_HH = {t['threshold_db']} dB ({t['method']}), baseline {bp['date']}")
    thr = thr_by_track.get(passes[0]["track"]) if passes else None    # headline (first track), kept for old readers

    # --- same-track pairs
    pair_results, overlays = {}, []

    def add(name, rgba, label, group, extra=None, prof_override=None):
        b = write_png_4326(od / "overlays" / f"{name}.png", rgba, prof_override or prof)
        overlays.append({"id": name, "label": label, "group": group, "url": f"overlays/{name}.png", "bounds": b, **(extra or {})})

    for pr in PAIRS:
        kb, ka = (pr["track"], pr["before"]), (pr["track"], pr["after"])
        if kb not in by_key or ka not in by_key:
            print(f"[pair] {pr['id']}: missing {pr['before'] if kb not in by_key else pr['after']} on {pr['track']}, skipped")
            continue
        later = [p for p in passes if p["track"] == pr["track"] and p["date"] > pr["after"]]
        before, after = load_pass(by_key[kb], prof), load_pass(by_key[ka], prof)
        confirm = load_pass(later[0], prof) if later else None
        is_eros = pr["id"].startswith("erosion")
        tthr = thr_by_track[pr["track"]]
        ch = wt.change(before, after, px, tthr["threshold_db"], river, confirm if is_eros else None, erosion=is_eros)
        m = ch.pop("masks"); by_t = ch.pop("masks_by_threshold")
        info = {"pair": pr, **ch, "confirm_pass": later[0]["date"] if (later and is_eros) else None,
                "receipts": {"before": by_key[kb]["receipt"], "after": by_key[ka]["receipt"]},
                "threshold": tthr, "code_version": CODE_VERSION}
        if is_eros:
            info["caveat"] = wt.CAVEAT
            info["exposure"] = exposure.pair_exposure(aoi, prof, pr, info, m, od, before, after)
            e = info["exposure"]["mainland_bank_loss"]
            print(f"[exposure] {pr['id']}: {e['sites']} sites, {e['area_ha']} ha, buildings {e['buildings']}, "
                  f"land cover {e['land_cover']['ha'] if e['land_cover'] else None}")
        (od / "pairs" / f"{pr['id']}.json").write_text(json.dumps(info, indent=1))
        pair_results[pr["id"]] = {"info": info, "masks": m, "by_t": by_t}
        write_tif(od / "layers" / f"{pr['id']}_n2o.tif", m["n2o"].astype("uint8"), prof, "uint8", 255)
        write_tif(od / "layers" / f"{pr['id']}_dist_new_water_m.tif",
                  (ndimage.distance_transform_edt(~m["n2o"]) * px).astype("float32") if m["n2o"].any()
                  else np.full(m["n2o"].shape, np.nan, "float32"), prof)
        # (the R=HH G=HV false-colour overlays are no longer written: the map uses the greyscale ones, ~20 MB each saved)
        for side, sc in (("before", before), ("after", after)):
            add(f"{pr['id']}_{side}_grey", grey_rgba(sc["hh"]), f"NISAR {pr[side]} {pr['track']} radar (greyscale)", "sar_grey",
                {"pair": pr["id"], "side": side})
        add(f"{pr['id']}_new_water", mask_rgba(m["n2o"], "00bcd4"), f"New water {pr['before']} to {pr['after']}", "change", {"pair": pr["id"]})
        if is_eros:
            add(f"{pr['id']}_eroded", mask_rgba(m["eroded"], "ff1744"),
                f"Mainland bank loss {pr['before']} to {pr['after']}" + ("" if ch["bank_loss_confirmed"] else " (UNCONFIRMED)"),
                "change", {"pair": pr["id"], "legend": [["ff1744", "mainland bank loss"]]})
        add(f"{pr['id']}_char_change", two_rgba(m["char_lost"], "ff9100", m["char_gained"], "ffea00"),
            f"Char (island) change {pr['before']} to {pr['after']}: orange lost, yellow gained", "change",
            {"pair": pr["id"], "legend": [["ff9100", "char land lost"], ["ffea00", "char land gained"]]})
        if m["flooded_veg"] is not None:
            add(f"{pr['id']}_flooded_veg", mask_rgba(m["flooded_veg"], "e040fb"), f"Flooded vegetation {pr['after']} (experimental)", "change", {"pair": pr["id"]})
        print(f"[pair] {pr['id']}: new water {ch['new_water_km2_range']} km2, mainland bank loss "
              f"{ch['mainland_bank_loss_ha_range']} ha, char change {ch['char_area_change_ha_range']} ha, "
              f"other new water {ch['other_new_water_km2_range']} km2, flooded veg {ch['flooded_vegetation_km2_range']} km2")

    # --- water extent per date (clean blue layer for the date slider), every full-track pass
    bl_dir = od / "banklines"; bl_dir.mkdir(exist_ok=True)
    water_by_date = {}
    for p in passes:
        wp = load_pass(p, prof)
        wcl = wt.classify(wp["hh"], wp["hv"], thr_by_track[p["track"]]["threshold_db"], px)
        wm = wcl["open_water"]
        water_by_date[(p["track"], p["date"])] = wm
        add(f"water_{p['date']}_{p['track']}", mask_rgba(wm, "1e78ff"), f"Water {p['date']} {p['track']}", "water_date",
            {"date": p["date"], "track": p["track"], "water_km2": round(float(wm.sum()) * px * px / 1e6, 1)})
        # per-date mainland bankline (for "Compare dates"), same rules as the pairs
        mainland, _ = wt.land_parts(wm, wcl["valid"], px)
        lines = exposure.bankline(mainland, wt.main_channel(wm, river), prof)
        gj = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"track": p["track"], "date": p["date"]},
             "geometry": transform_geom(prof["crs"], "EPSG:4326", {"type": "LineString", "coordinates": ln}, precision=6)}
            for ln in lines]}
        (bl_dir / f"bankline_{p['track']}_{p['date']}.geojson").write_text(json.dumps(gj))

    # --- InSAR coherence between consecutive passes (src/acquire/gunw_coherence.py): observation layer only
    for ct in sorted((dem_dir.parents[1] / "coherence" / aoi).glob("coh_*.tif")):
        _, tr, d1, d2 = ct.stem.split("_")
        coh = to_grid(ct, prof)
        a = np.where(np.isfinite(coh), np.clip((0.35 - coh) / 0.25, 0, 1) * 230, 0)        # only coherence < 0.35 shows
        for d in (d1, d2):                    # open water always decorrelates: hide it, show changed LAND only
            if (tr, d) in water_by_date:
                a[water_by_date[(tr, d)]] = 0
        a[river] = 0
        rgba = np.dstack([np.full(coh.shape, 255), np.full(coh.shape, 120), np.full(coh.shape, 0), a]).astype("uint8")
        add(f"coh_{tr}_{d1}_{d2}", rgba, f"Surface change {d1} to {d2} (InSAR coherence, {tr})", "coherence",
            {"track": tr, "d1": d1, "d2": d2, "median_coherence": round(float(np.nanmedian(coh)), 2),
             "low_pct": round(float(np.nanmean(coh < 0.3) * 100), 1)})

    # --- wetness now: newest full-track pass
    latest = passes[-1] if passes else None
    wet_now = np.zeros_like(river)
    if latest:
        lp = load_pass(latest, prof)
        wet_now = wt.classify(lp["hh"], lp["hv"], thr_by_track[latest["track"]]["threshold_db"], px)["open_water"] & ~river

    # --- 7-day layer (experimental planning layer, never an official warning)
    rain = get_rain(lat, lon)
    if replay:
        _season_replay(aoi, passes, prof, thr_by_track, river, hand, dist_river, lat, lon, rain)
    elif calibrate and latest:
        _calibrate_on(aoi, latest, prof, thr_by_track, river, hand, dist_river, lat, lon, rain)
    prm = fp.load_params(aoi)
    prob = fp.probability_7d(hand, dist_river, wet_now, rain["antecedent_mm"], rain["forecast_mm"],
                             rain["baseline_heavy_p90_mm"], prm)
    prob[:, river] = np.nan

    # --- base layers + overlays
    if (dem_dir / "s2_rgb.tif").exists():
        rgb = np.dstack([to_grid(dem_dir / "s2_rgb.tif", prof, Resampling.nearest, b) for b in (1, 2, 3)])
        add("optical_s2", np.dstack([np.nan_to_num(rgb), np.where(np.isfinite(rgb[..., 0]), 255, 0)]).astype("uint8"),
            "Sentinel-2 optical (dry season)", "base")
    # cloud-free Sentinel-2 per radar date (src/acquire/gee_optical.py); unfilled pixels transparent -> Esri shows
    opt_dir = dem_dir.parents[1] / "optical" / aoi
    # preferred: ONE whole clear scene per radar date (src/acquire/gee_scene.py), shared files when dates share a day
    scene_recs = [json.loads(p.read_text()) for p in sorted(opt_dir.glob("scene_for_*.json"))]
    done_files = {}
    for sc in scene_recs:
        if sc.get("status") != "ok":
            continue
        name = f"scene_{sc['sensor']}_{sc['day']}"
        if name not in done_files:
            with rasterio.open(opt_dir / sc["rgb"]) as s:
                rgb = s.read(); pS = {"crs": s.crs, "transform": s.transform, "width": s.width, "height": s.height}
            rgba = np.dstack([rgb[0], rgb[1], rgb[2], np.where(rgb.any(axis=0), 255, 0)]).astype("uint8")
            b = write_webp_4326(od / "overlays" / f"{name}.webp", rgba, pS)
            done_files[name] = b
            del rgb, rgba                      # 10 m scenes are large: free before the next step
            import gc; gc.collect()
        overlays.append({"id": f"optical_{sc['radar_date']}", "label": sc["label"], "group": "optical_date",
                         "url": f"overlays/{name}.webp", "bounds": done_files[name], "date": sc["radar_date"],
                         "scene_day": sc["day"], "sensor": sc["sensor"], "days_offset": sc["days_offset"],
                         "aoi_cloud_pct": sc["aoi_cloud_pct"], "scene_ids": sc["scene_ids"]})
    for rcp in ([] if scene_recs else sorted(opt_dir.glob("s2cf_*_receipt.json"))):   # legacy pixel composites
        orc = json.loads(rcp.read_text())
        with rasterio.open(opt_dir / orc["rgb"]) as s, rasterio.open(opt_dir / orc["days"]) as sd:
            rgb = s.read(); dd = sd.read(1); p20 = {"crs": s.crs, "transform": s.transform, "width": s.width, "height": s.height}
        rgba = np.dstack([rgb[0], rgb[1], rgb[2], np.where((dd < 255) & rgb.any(axis=0), 255, 0)]).astype("uint8")
        add(f"optical_{orc['target_date']}", rgba,
            f"Optical, cloud-free composite for {orc['target_date']} (nearest clear pixels, median offset "
            f"{orc['median_offset_days']} d, {orc['unfilled_pct']}% unfilled)", "optical_date",
            {"date": orc["target_date"], "median_offset_days": orc["median_offset_days"], "unfilled_pct": orc["unfilled_pct"],
             "mask": orc["mask"], "n_scenes": orc["n_scenes"]}, prof_override=p20)
    # Sentinel-2 L2A before/after true colour (legacy receipts, if present)
    for side in ("before", "after"):
        rcp = opt_dir / f"s2_{side}_receipt.json"
        if not rcp.exists():
            continue
        orc = json.loads(rcp.read_text())
        with rasterio.open(opt_dir / orc["tif"]) as s:
            rgb = s.read(); p10 = {"crs": s.crs, "transform": s.transform, "width": s.width, "height": s.height}
        rgba = np.dstack([rgb[0], rgb[1], rgb[2], np.where(rgb.any(axis=0), 255, 0)]).astype("uint8")
        add(f"optical_{side}", rgba, f"Sentinel-2 {orc['date']} ({side}, AOI cloud {orc['aoi_cloud_pct']}%)", "optical",
            {"side": side, "date": orc["date"], "receipt": {k: orc[k] for k in ("scenes", "aoi_cloud_pct", "source")}},
            prof_override=p10)
    add("river_khal", mask_rgba(river, "0055ff"), "River (FALLBACK: NISAR persistent water)" if terrain_rc.exists()
        else "River / khal (permanent channel)", "water")
    if latest:
        add("water_latest", mask_rgba(wet_now, "00e5ff"), f"Water beyond channel, {latest['date']} {latest['track']}", "water")
    add("hand", colorize(hand, 0, 15, ["d73027", "fc8d59", "fee08b", "d9ef8b", "1a9850"]),
        "Height above river (FALLBACK: GLO-30 nearest-river height, m)" if terrain_rc.exists() else "Height above river (HAND, m)", "dem")
    write_tif(od / "layers" / "hand_m.tif", hand, prof)
    if dem is not None:
        write_tif(od / "layers" / "dem_m.tif", dem, prof)
    write_tif(od / "layers" / "dist_river_m.tif", dist_river, prof)
    write_tif(od / "layers" / "river_mask.tif", river.astype("uint8"), prof, "uint8", 255)
    for i, day in enumerate(rain["forecast_dates"]):
        write_tif(od / "layers" / f"prob_day{i + 1}.tif", np.nan_to_num(prob[i] * 100, nan=255), prof, "uint8", 255)
        add(f"prob_day{i + 1}", colorize(prob[i], 0, 1, ["1a9850", "fee08b", "fc8d59", "d73027"], prob[i] >= 0.2),
            f"Experimental flood likelihood {day}", "forecast")

    feats = []
    for geom, _ in features.shapes(river.astype("uint8"), mask=river, transform=prof["transform"]):
        if len(geom["coordinates"][0]) < 8:
            continue
        g = transform_geom(prof["crs"], "EPSG:4326", geom, precision=5)
        feats.append({"type": "Feature", "properties": {"class": "river_khal"}, "geometry": g})
    (od / "river_khal.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}))

    # --- summary
    hist = prm.history
    land = ~river & np.isfinite(hand)
    pa = px * px / 1e6
    now = dt.datetime.now(dt.timezone.utc)
    acq = latest["receipt"].get("acquired_utc") if latest else None
    summary = {
        "aoi": aoi, "label": cfg["label"], "bbox": cfg["bbox"], "grid_m": px, "code_version": CODE_VERSION,
        "generated_utc": now.isoformat(timespec="minutes"),
        "threshold": thr,
        "thresholds_by_track": thr_by_track,
        "pairs": {k: v["info"] for k, v in pair_results.items()},
        "latest_pass": None if not latest else {
            "date": latest["date"], "track": latest["track"], "acquired_utc": acq,
            "data_age_hours": round((now - dt.datetime.fromisoformat(acq.replace("Z", "+00:00"))).total_seconds() / 3600)
            if acq else None,
            "water_beyond_channel_km2": round(float(wet_now.sum()) * pa, 2)},
        "passes_available": [f"{p['date']} {p['track']}" for p in passes],
        "radar_gap": {"utc": NISAR_GAP_UTC, "note": "No NISAR data; shown as a gap, never interpolated"},
        "experimental_7day": {
            "label": "Experimental planning layer, not an official warning (official forecasts: FFWC/BMD)",
            "days": [{"date": d, "rain_mm": r, "area_p50_km2": round(float((prob[i][land] >= 0.5).sum()) * pa, 2)}
                     for i, (d, r) in enumerate(zip(rain["forecast_dates"], rain["forecast_mm"]))],
            "calibration": {"bias": round(prm.bias, 3), "passes_used": len(hist),
                            "error_margin_pct": hist[-1]["error_margin_pct"] if hist else None,
                            "history": hist, "status": "calibrated" if hist else "UNCALIBRATED priors"}},
        "weather": {k: rain[k] for k in rain if k not in ("lat", "lon")},
        "sources": sources,
    }
    (od / "summary.json").write_text(json.dumps(summary, indent=1))
    (od / "overlays.json").write_text(json.dumps(overlays, indent=1))
    unions = _union_summary(aoi, prof, pair_results, prob, summary)
    print(f"[run] {aoi}: {len(pair_results)} pairs, {len(overlays)} overlays, {len(unions)} unions -> {od}")
    return summary


def _calibrate_on(aoi, p, prof, thr, river, hand, dist_river, lat, lon, rain):
    prm = fp.load_params(aoi)
    if p["date"] in {h["pass_date"] for h in prm.history}:
        print(f"[calib] {p['date']} already used"); return
    if in_gap(p["date"]):
        print(f"[calib] {p['date']} is inside the radar gap, skipped"); return
    try:
        mm = observed_rain(lat, lon, p["date"])["mm"]
    except Exception as exc:
        print(f"[calib] no NASA POWER rain for {p['date']} ({exc!r}); using current antecedent rain")
        mm = rain["antecedent_mm"]
    ri = fp.rain_index([], mm, rain["baseline_heavy_p90_mm"], prm.k)[-1]
    lp = load_pass(p, prof)
    observed = wt.classify(lp["hh"], lp["hv"], thr[p["track"]]["threshold_db"], prof["transform"].a)["open_water"] & ~river
    entry = fp.calibrate(aoi, ri, hand, dist_river, np.zeros_like(river), observed,
                         ~river & np.isfinite(hand), p["date"], prm)
    sb, sa = entry["skill_before"], entry["skill_after"]
    print(f"[calib] {p['date']} {p['track']}: obs wet {sa['obs_flood_frac']}, error margin {entry['error_margin_pct']}%, "
          f"Brier {sb['brier']} -> {sa['brier']}, BSS {sb['brier_skill_score']} -> {sa['brier_skill_score']}, "
          f"CSI@freq-matched {sb['csi']} -> {sa['csi']} (cut {sb['cutoff']} -> {sa['cutoff']})")


def _season_replay(aoi, passes, prof, thr, river, hand, dist_river, lat, lon, rain):
    fp.save_params(aoi, fp.Params())       # start clean, then walk the season in order
    for p in passes:
        _calibrate_on(aoi, p, prof, thr, river, hand, dist_river, lat, lon, rain)


def _union_summary(aoi, prof, pair_results, prob, summary):
    """Per-union numbers in the team's union_summary contract (fields this pipeline owns)."""
    od = out_dir(aoi)
    path = VECTOR / "unions.geojson"
    if not path.exists():
        return []
    gj = json.loads(path.read_text(encoding="utf-8"))
    pa = prof["transform"].a ** 2 / 1e6
    flood = next((v for k, v in pair_results.items() if k.startswith("rise")), None)
    eros = next((v for k, v in pair_results.items() if k.startswith("erosion")), None)
    out = []
    for ftr in gj["features"]:
        props = ftr.get("properties", {})
        geom = transform_geom("EPSG:4326", prof["crs"], ftr["geometry"])
        inside = features.geometry_mask([geom], (prof["height"], prof["width"]), prof["transform"], invert=True)
        if not inside.any():
            continue

        def rng(v, key, scale):
            if v is None or v["by_t"][0][key] is None:
                return None
            vals = [float((m[key] & inside).sum()) * pa * scale for m in v["by_t"]]
            return [round(min(vals), 3), round(max(vals), 3)]
        def char_rng(v):
            if v is None:
                return None
            vals = [float(((m["char_before"] & inside).sum() - (m["char_after"] & inside).sum())) * pa * 100 for m in v["by_t"]]
            return [round(min(vals), 3), round(max(vals), 3)]
        rows, cols = np.nonzero(inside)
        cx, cy = prof["transform"] * (cols.mean(), rows.mean())
        c = transform_geom(prof["crs"], "EPSG:4326", {"type": "Point", "coordinates": [cx, cy]})
        fi = flood["info"] if flood else None
        pin = np.where(inside, prob, np.nan)
        out.append({
            "union_id": props.get("shapeID") or props.get("id"),
            "union_name_en": props.get("shapeName") or props.get("name"),
            "upazila_name_en": props.get("upazila"),
            "coordinates": {"lat": round(c["coordinates"][1], 5), "lon": round(c["coordinates"][0], 5), "crs": "EPSG:4326"},
            "status": None,   # set by the rule engine, not here
            "data_age_hours": (summary["latest_pass"] or {}).get("data_age_hours"),
            "nisar_observation": {
                "pass_date_utc": fi["receipts"]["after"].get("acquired_utc") if fi else None,
                "baseline_date_utc": fi["receipts"]["before"].get("acquired_utc") if fi else None,
                "new_water_km2_range": rng(flood, "n2o", 1),
                "flooded_vegetation_km2_range": rng(flood, "flooded_veg", 1),
                "mainland_bank_loss_ha_range": rng(eros, "eroded", 100),
                "erosion_ha_range_jun_oct": rng(eros, "eroded", 100),     # DEPRECATED alias of mainland_bank_loss_ha_range
                "bank_loss_confirmed": eros["info"]["bank_loss_confirmed"] if eros else None,
                "char_area_change_ha_range": char_rng(eros),
                "other_new_water_km2_range": rng(eros, "other_new_water", 1),
                "unknown_pixel_pct": fi["unknown_pixel_pct"] if fi else None,
                "caveat": eros["info"]["caveat"] if eros else None,
            },
            "experimental_7day_max_pct": round(float(np.nanmax(pin)) * 100, 1) if np.isfinite(pin).any() else None,
            "evidence_receipt": _receipt(fi, summary),
        })
    (od / "union_summary.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    return out


def _receipt(fi, summary):
    if not fi:
        return {"radar_gap_flag": summary["radar_gap"]["note"]}
    a = fi["receipts"]["after"]
    return {"granule_id": a.get("granule_id"), "cmr_id": a.get("cmr_id"), "processing_level": a.get("processing_level"),
            "water_rule": f"HH < {fi['threshold_db']} dB (tested at +/- 1 dB), HV noise floor masked at -23 dB",
            "threshold_method": fi["threshold"].get("method"),
            "radar_gap_flag": f"No NISAR GCOV {NISAR_GAP_UTC[0][:10]} to {NISAR_GAP_UTC[1][:10]}; shown, never interpolated",
            "code_version": CODE_VERSION}


def location_status(aoi: str, lat: float, lon: float) -> dict:
    """What the API returns for a user location (team contract shape, fields this pipeline owns)."""
    od = out_dir(aoi)

    def sample(name):
        p = od / "layers" / name
        if not p.exists():
            return None
        with rasterio.open(p) as s:
            x, y = warp_xy("EPSG:4326", s.crs, [lon], [lat])
            r, c = s.index(x[0], y[0])
            if not (0 <= r < s.height and 0 <= c < s.width):
                return None
            v = float(s.read(1, window=((r, r + 1), (c, c + 1)))[0, 0])
            return None if (s.nodata is not None and v == s.nodata) or not np.isfinite(v) else v

    summ = json.loads((od / "summary.json").read_text())
    flood_id = next((k for k in summ["pairs"] if k.startswith("rise")), next(iter(summ["pairs"]), None))
    eros_id = next((k for k in summ["pairs"] if k.startswith("erosion")), None)
    fi = summ["pairs"].get(flood_id) if flood_id else None
    days = summ["experimental_7day"]["days"]
    acq = fi["receipts"]["after"].get("acquired_utc") if fi else None
    local = None
    if acq:
        local = (dt.datetime.fromisoformat(acq.replace("Z", "+00:00")) + dt.timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%S+06:00")
    near = sample(f"{flood_id}_dist_new_water_m.tif") if flood_id else None
    return {
        "coordinates": {"lat": lat, "lon": lon, "crs": "EPSG:4326"},
        "status": None,
        "data_age_hours": (summ["latest_pass"] or {}).get("data_age_hours"),
        "in_river_or_khal": sample("river_mask.tif") == 1,
        "nisar_observation": {
            "pass_date_utc": acq, "pass_date_local": local,
            "baseline_date_utc": fi["receipts"]["before"].get("acquired_utc") if fi else None,
            "new_water_km2_range": fi["new_water_km2_range"] if fi else None,
            "flooded_vegetation_km2_range": fi["flooded_vegetation_km2_range"] if fi else None,
            "mainland_bank_loss_ha_range": summ["pairs"][eros_id]["mainland_bank_loss_ha_range"] if eros_id else None,
            "erosion_ha_range": summ["pairs"][eros_id]["mainland_bank_loss_ha_range"] if eros_id else None,  # DEPRECATED alias
            "bank_loss_confirmed": summ["pairs"][eros_id]["bank_loss_confirmed"] if eros_id else None,
            "char_area_change_ha_range": summ["pairs"][eros_id]["char_area_change_ha_range"] if eros_id else None,
            "caveat": summ["pairs"][eros_id].get("caveat") if eros_id else None,
            "unknown_pixel_pct": fi["unknown_pixel_pct"] if fi else None,
            "nearest_new_water_m": None if near is None else round(near),
        },
        "terrain": {"height_above_river_m": sample("hand_m.tif"), "elevation_m": sample("dem_m.tif"),
                    "dem_datum": "Copernicus GLO-30, EGM2008 geoid", "distance_to_river_m": sample("dist_river_m.tif"),
                    "height_above_river_source": summ.get("sources", {}).get("hand"),
                    "terrain_fallback": bool(summ.get("sources", {}).get("terrain_fallback"))},
        "experimental_7day": {"label": summ["experimental_7day"]["label"],
                              "days": [{"date": d["date"], "pct": sample(f"prob_day{i + 1}.tif")} for i, d in enumerate(days)],
                              "error_margin_pct": summ["experimental_7day"]["calibration"]["error_margin_pct"]},
        "evidence_receipt": _receipt(fi, summ),
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--aoi", default="kazipur")
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--replay", action="store_true")
    a = ap.parse_args()
    run(a.aoi, a.calibrate, a.replay)
