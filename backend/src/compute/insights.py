"""Insights: statistics behind the map, all deterministic, all from the pipeline's own outputs.

  python -m src.compute.insights --aoi kazipur

Writes outputs/<aoi>/insights/insights.json, one CSV per section, and the "times under water" overlay.
Sections: river (water area vs discharge), frequency (times under water, cropland and buildings in water),
bankloss_time (cumulative mainland bank loss vs 18 Jun, west/east), where (by union/upazila), near_bank
(exposure close to an actively retreating bank: an observation, not a forecast), retreat (top-10 site retreat per
pass), learned (sentences generated from these numbers).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json

import numpy as np
import rasterio
from rasterio import features
from rasterio.warp import Resampling, transform as warp_xy, transform_geom
from scipy import ndimage

from src.compute import water as wt
from src.config import AOIS, VECTOR, aoi_dir, base_profile, out_dir

TRACK = "069A"
STAGE_RATIO = 1.3
BUFFERS = (50, 100, 200, 500)
EIGHT = np.ones((3, 3), bool)
BLD_CAVEAT = "Buildings are model-detected footprints from older imagery (what stood there before), not a damage count."
STAGE_CAVEAT = ("River stage differs between dates: land-to-water change near the bank includes water level. "
                "Passes whose flow differs > 1.3x from 18 Jun are greyed.")


def _d(s):
    return dt.date(int(s[:4]), int(s[4:6]), int(s[6:]))


def _csv(path, rows):
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)


def _px(prof, lon, lat):
    xs, ys = warp_xy("EPSG:4326", prof["crs"], np.atleast_1d(lon).tolist(), np.atleast_1d(lat).tolist())
    c, r = ~prof["transform"] * (np.asarray(xs), np.asarray(ys))
    return np.floor(r).astype(int), np.floor(c).astype(int)


def _rasterize(gj, prof):
    shapes = [(transform_geom("EPSG:4326", prof["crs"], f["geometry"]), i + 1) for i, f in enumerate(gj["features"])]
    if not shapes:
        return np.zeros((prof["height"], prof["width"]), "int32")
    return features.rasterize(shapes, out_shape=(prof["height"], prof["width"]), transform=prof["transform"], dtype="int32")


def _bankline(water, valid, river, px):
    mainland, _ = wt.land_parts(water, valid, px)
    ch = wt.main_channel(water, river)
    return mainland, mainland & ndimage.binary_dilation(ch, structure=EIGHT)


def run(aoi="kazipur") -> dict:
    from src.compute.compare import compare
    from src.compute.exposure import load_buildings, worldcover
    from src.compute.forecast import glofas
    from src.compute.water_ml import rain_series
    from src.pipeline.run_aoi import list_passes, load_pass, to_grid, write_png_4326
    prof = base_profile(aoi); px = AOIS[aoi]["grid_m"]; pa_ha = px * px / 1e4
    od = out_dir(aoi); idir = od / "insights"; idir.mkdir(exist_ok=True)
    summ = json.loads((od / "summary.json").read_text())
    thr = summ["thresholds_by_track"][TRACK]["threshold_db"]
    river = to_grid(aoi_dir(aoi, "dem") / "river_mask.tif", prof, Resampling.nearest) >= 0.5
    passes = [p for p in list_passes(aoi) if p["track"] == TRACK]
    dates = [p["date"] for p in passes]
    newest = dates[-1]
    Q = glofas(aoi, (_d(newest) + dt.timedelta(days=30)).strftime("%Y-%m-%d"))
    qd = {t: (None if not np.isfinite(v) else float(v)) for t, v in zip(Q["time"], Q["q"])}
    rain, clim = rain_series(aoi)
    wc = worldcover(aoi, prof)
    bld, _ = load_buildings(aoi)
    br, bc = _px(prof, bld["lon"], bld["lat"]) if bld is not None else (np.array([], int), np.array([], int))
    bok = (br >= 0) & (br < prof["height"]) & (bc >= 0) & (bc < prof["width"])
    br, bc = br[bok], bc[bok]

    water, valid = {}, {}
    for p in passes:
        lp = load_pass(p, prof)
        c = wt.classify(lp["hh"], lp["hv"], thr, px)
        water[p["date"]], valid[p["date"]] = c["open_water"], c["valid"]
    q0 = qd.get(dates[0])

    # 1. river behaviour
    river_rows = []
    for d in dates:
        w = water[d]
        river_rows.append({"date": d, "water_km2": round(float(w.sum()) * px * px / 1e6, 1),
                           "water_outside_channel_km2": round(float((w & ~river).sum()) * px * px / 1e6, 1),
                           "discharge_m3s": round(qd[d]) if qd.get(d) else None,
                           "rain_7d_mm": round(sum(rain.get((_d(d) - dt.timedelta(days=k)).strftime("%Y%m%d"), clim) for k in range(7)), 1)})
    x = np.array([r["discharge_m3s"] for r in river_rows], float); y = np.array([r["water_km2"] for r in river_rows], float)
    m = np.isfinite(x) & np.isfinite(y)
    slope, icpt = np.polyfit(x[m], y[m], 1); r2 = float(np.corrcoef(x[m], y[m])[0, 1] ** 2)
    daily = [{"date": t, "discharge_m3s": round(qd[t]) if qd.get(t) else None,
              "rain_mm": round(rain.get(t, float("nan")), 1) if t in rain else None}
             for t in Q["time"] if dates[0] <= t <= (_d(newest) + dt.timedelta(days=30)).strftime("%Y%m%d")]
    river_sec = {"passes": river_rows, "daily": daily, "gap": ["20260727", "20260810"],
                 "fit": {"slope_km2_per_1000m3s": round(slope * 1000, 2), "intercept_km2": round(icpt, 1), "r2": round(r2, 2), "n": int(m.sum())},
                 "takeaway": (f"Each extra 1,000 m³/s of Jamuna flow puts about {slope * 1000:.1f} km² more under water "
                              f"(linear fit over {int(m.sum())} radar passes, R² {r2:.2f})."
                              + ("" if r2 >= 0.4 else " The relationship is weak: water extent also depends on whether the flood is "
                                 "rising or falling and on local rain, so treat this number with caution.")),
                 "reliable": r2 >= 0.4}
    _csv(idir / "river_passes.csv", river_rows); _csv(idir / "river_daily.csv", daily)

    # 2. inundation frequency
    n = len(dates)
    freq = np.zeros(river.shape, "int16")
    for d in dates:
        freq += (water[d] & ~river)
    hist = [{"times_under_water": k, "area_ha": round(float((freq == k).sum()) * pa_ha, 1)} for k in range(1, n + 1)]
    classes = [("1-2 times", 1, 2), ("3-5 times", 3, 5), (f"6-{n} times", 6, n)]
    crop = (wc == 40) if wc is not None else np.zeros(river.shape, bool)
    crop_freq = [{"class": c, "cropland_ha": round(float((crop & (freq >= a) & (freq <= b)).sum()) * pa_ha, 1)} for c, a, b in classes]
    bld_in_water = [{"date": d, "buildings_in_water": int(water[d][br, bc].sum()),
                     "cropland_in_water_ha": round(float((crop & water[d] & ~river).sum()) * pa_ha, 1)} for d in dates]
    rgba = np.zeros(freq.shape + (4,), "uint8")
    ramp = np.array([[198, 219, 239], [158, 202, 225], [107, 174, 214], [66, 146, 198], [33, 113, 181],
                     [8, 81, 156], [8, 48, 107], [37, 37, 120], [60, 20, 110], [80, 10, 90]], "uint8")
    for k in range(1, n + 1):
        sel = freq == k
        rgba[sel, :3] = ramp[min(k, len(ramp)) - 1]; rgba[sel, 3] = 210
    fb = write_png_4326(idir / "times_under_water.png", rgba, prof)
    peak = max(bld_in_water, key=lambda r: r["cropland_in_water_ha"])
    freq_sec = {"n_passes": n, "histogram": hist, "cropland_by_class": crop_freq, "by_date": bld_in_water,
                "overlay": {"url": "insights/times_under_water.png", "bounds": fb},
                "caveat": BLD_CAVEAT + " Permanent river channel excluded.",
                "takeaway": f"Flooded cropland peaked at {peak['cropland_in_water_ha']:,.0f} ha on {_d(peak['date']).strftime('%d %b')}; "
                            f"{crop_freq[2]['cropland_ha']:,.0f} ha of cropland was under water 6 or more of the {n} passes."}
    _csv(idir / "frequency_histogram.csv", hist); _csv(idir / "frequency_by_date.csv", bld_in_water)

    # river centre per row (for west / east bank)
    cols = np.arange(river.shape[1])
    cnt = river.sum(axis=1)
    centre = np.where(cnt > 0, (river * cols).sum(axis=1) / np.maximum(cnt, 1), np.nan)
    centre = np.interp(np.arange(len(centre)), np.flatnonzero(np.isfinite(centre)), centre[np.isfinite(centre)])

    def side_of(lat, lon):
        r, c = _px(prof, lon, lat)
        r = int(np.clip(r[0], 0, river.shape[0] - 1)); return "west" if c[0] < centre[r] else "east"

    # 3. bank loss through time (vs 18 Jun), precomputed compares
    bl_rows = []
    for d in dates[1:]:
        try:
            info = compare(aoi, TRACK, dates[0], d)
        except Exception:
            continue
        gj = json.loads((od / "pairs" / f"{info['pair']['id']}_sites.geojson").read_text())
        sides = {"west": 0.0, "east": 0.0}
        for f in gj["features"]:
            sides[side_of(f["properties"]["lat"], f["properties"]["lon"])] += f["properties"]["area_ha"]
        ratio = max(q0, qd[d]) / min(q0, qd[d]) if q0 and qd.get(d) else None
        bl_rows.append({"date": d, "bank_loss_ha_low": info["mainland_bank_loss_ha_range"][0],
                        "bank_loss_ha_high": info["mainland_bank_loss_ha_range"][1], "bank_loss_ha_mid": info["mainland_bank_loss_ha_mid"],
                        "west_bank_ha": round(sides["west"], 1), "east_bank_ha": round(sides["east"], 1),
                        "confirmed": info["bank_loss_confirmed"], "discharge_m3s": round(qd[d]) if qd.get(d) else None,
                        "flow_ratio_vs_18jun": round(ratio, 2) if ratio else None, "comparable_flow": bool(ratio and ratio < STAGE_RATIO)})
    comp = [r for r in bl_rows if r["comparable_flow"]]
    bl_take = None
    if comp:
        last = comp[-1]
        more = "west" if last["west_bank_ha"] > last["east_bank_ha"] else "east"
        bl_take = (f"At comparable river flow ({_d(last['date']).strftime('%d %b')}), {last['bank_loss_ha_low']:.0f}-{last['bank_loss_ha_high']:.0f} ha "
                   f"of mainland bank had been lost since 18 Jun; the {more} bank lost more "
                   f"({max(last['west_bank_ha'], last['east_bank_ha']):.0f} vs {min(last['west_bank_ha'], last['east_bank_ha']):.0f} ha in mapped sites).")
    # erosion cannot un-happen: if a later comparable pass shows much less loss than an earlier one, the earlier
    # value was inundation, not bank loss -> say so instead of hiding it
    jumps = [(a, b) for a, b in zip(comp, comp[1:]) if b["bank_loss_ha_mid"] < 0.7 * a["bank_loss_ha_mid"]]
    caveat = STAGE_CAVEAT
    if jumps:
        peaks = ", ".join(f"{_d(a['date']).strftime('%d %b')} ({a['bank_loss_ha_mid']:.0f} ha)" for a, _ in jumps)
        caveat += (f" Even at similar flow the curve is not cumulative: {peaks} later drops back, so those values include "
                   "floodplain water behind the bank (rising vs falling river), not only erosion. The latest comparable "
                   "pass is the best estimate.")
    bl_sec = {"rows": bl_rows, "caveat": caveat, "takeaway": bl_take, "non_monotonic_passes": [a["date"] for a, _ in jumps]}
    _csv(idir / "bankloss_through_time.csv", bl_rows)

    # 4. where (headline confirmed pair)
    head = "erosion_069A_interim" if (od / "pairs" / "erosion_069A_interim_sites.geojson").exists() else "erosion_069A"
    hsites = json.loads((od / "pairs" / f"{head}_sites.geojson").read_text())
    hinfo = json.loads((od / "pairs" / f"{head}.json").read_text())
    by_u = {}
    for f in hsites["features"]:
        q = f["properties"]; k = (q.get("union") or "unknown", q.get("upazila") or "")
        u = by_u.setdefault(k, {"union": k[0], "upazila": k[1], "sites": 0, "bank_loss_ha": 0.0, "cropland_ha": 0.0,
                                "buildings": 0, "largest_site": None, "largest_ha": 0.0, "lat": q["lat"], "lon": q["lon"]})
        u["sites"] += 1; u["bank_loss_ha"] += q["area_ha"]
        u["cropland_ha"] += (q.get("land_cover") or {}).get("ha", {}).get("cropland", 0.0)
        u["buildings"] += q.get("building_count") or 0
        if q["area_ha"] > u["largest_ha"]:
            u.update(largest_site=q["site_id"], largest_ha=q["area_ha"], lat=q["lat"], lon=q["lon"])
    where_rows = sorted(({**v, "bank_loss_ha": round(v["bank_loss_ha"], 1), "cropland_ha": round(v["cropland_ha"], 1)}
                         for v in by_u.values()), key=lambda r: -r["bank_loss_ha"])
    lc = hinfo["exposure"]["mainland_bank_loss"]["land_cover"]
    top = where_rows[0] if where_rows else None
    where_sec = {"pair": head, "pair_dates": [hinfo["pair"]["before"], hinfo["pair"]["after"]], "rows": where_rows, "land_cover": lc,
                 "takeaway": (f"{top['union']} ({top['upazila']}) lost the most mainland bank: {top['bank_loss_ha']:.0f} ha in "
                              f"{top['sites']} sites, {top['cropland_ha']:.0f} ha of it cropland, {top['buildings']} buildings.") if top else None}
    _csv(idir / "where_by_union.csv", where_rows)

    # 5. close to an actively retreating bank (observation): 16 Oct bankline near bank-loss sites of 18 Jun -> newest
    last_pair = f"erosion_{TRACK}" if (od / "pairs" / f"erosion_{TRACK}_sites.geojson").exists() else head
    lsites = json.loads((od / "pairs" / f"{last_pair}_sites.geojson").read_text())
    site_r = _rasterize(lsites, prof) > 0
    mainland_new, bank_new = _bankline(water[newest], valid[newest], river, px)
    near_sites = ndimage.binary_dilation(site_r, structure=EIGHT, iterations=int(300 / px))
    retreat_bank = bank_new & near_sites
    dist = ndimage.distance_transform_edt(~retreat_bank) * px if retreat_bank.any() else np.full(river.shape, np.inf)
    ulab = np.zeros(river.shape, "int32"); unames = [("", "")]
    if (VECTOR / "unions.geojson").exists():
        ug = json.loads((VECTOR / "unions.geojson").read_text(encoding="utf-8"))
        ulab = _rasterize(ug, prof)
        unames += [(f["properties"].get("shapeName"), f["properties"].get("upazila")) for f in ug["features"]]
    b_land = mainland_new[br, bc]; b_dist = dist[br, bc]
    near_rows, per_union = [], {}
    for b in BUFFERS:
        zone = mainland_new & (dist <= b)
        near_rows.append({"within_m": b, "buildings": int((b_land & (b_dist <= b)).sum()),
                          "cropland_ha": round(float((zone & crop).sum()) * pa_ha, 1)})
        bu = ulab[br, bc][b_land & (b_dist <= b)]
        for i, cnt_ in zip(*np.unique(bu, return_counts=True)):
            if i:
                per_union.setdefault(int(i), {})[f"buildings_{b}m"] = int(cnt_)
    pu_rows = sorted(({"union": unames[i][0], "upazila": unames[i][1], **{f"buildings_{b}m": v.get(f"buildings_{b}m", 0) for b in BUFFERS}}
                      for i, v in per_union.items()), key=lambda r: -r["buildings_100m"])
    slab, ns = ndimage.label(ndimage.binary_dilation(retreat_bank, structure=EIGHT, iterations=2), structure=EIGHT)
    stretches = []
    near100 = mainland_new & (dist <= 100)
    nearest_stretch = np.zeros(river.shape, "int32")
    if ns:
        _, (ri, ci) = ndimage.distance_transform_edt(slab == 0, return_indices=True)
        nearest_stretch = slab[ri, ci]
    for i, sl in enumerate(ndimage.find_objects(slab), 1):
        if sl is None:
            continue
        sel = (slab[sl] == i) & retreat_bank[sl]
        if sel.sum() < 5:
            continue
        rr, cc = np.nonzero(sel)
        x_, y_ = prof["transform"] * (cc.mean() + sl[1].start + 0.5, rr.mean() + sl[0].start + 0.5)
        ll = transform_geom(prof["crs"], "EPSG:4326", {"type": "Point", "coordinates": [x_, y_]})["coordinates"]
        zone = near100 & (nearest_stretch == i)
        nb = int((zone[br, bc]).sum())
        u = ulab[int(rr.mean() + sl[0].start), int(cc.mean() + sl[1].start)]
        stretches.append({"stretch": i, "length_m": int(sel.sum() * px), "buildings_within_100m": nb,
                          "cropland_within_100m_ha": round(float((zone & crop).sum()) * pa_ha, 1),
                          "union": unames[u][0] if u else None, "upazila": unames[u][1] if u else None,
                          "lat": round(ll[1], 5), "lon": round(ll[0], 5)})
    stretches = sorted(stretches, key=lambda s: (-s["buildings_within_100m"], -s["length_m"]))[:10]
    for k, s in enumerate(stretches, 1):
        s["rank"] = k
    nb100 = next(r for r in near_rows if r["within_m"] == 100)
    near_sec = {"bankline_date": newest, "based_on_pair": last_pair, "rows": near_rows, "by_union": pu_rows, "top_stretches": stretches,
                "label": "close to an actively retreating bank (observation, not a forecast)", "caveat": BLD_CAVEAT,
                "takeaway": f"{nb100['buildings']} buildings and {nb100['cropland_ha']:,.0f} ha of cropland stand within 100 m of a bank "
                            f"that retreated this season (bank line of {_d(newest).strftime('%d %b')})."}
    _csv(idir / "near_retreating_bank.csv", near_rows); _csv(idir / "near_bank_by_union.csv", pu_rows); _csv(idir / "near_bank_top_stretches.csv", stretches)

    # 6. site retreat per pass (top 10 sites of the headline pair)
    _, bank0 = _bankline(water[dates[0]], valid[dates[0]], river, px)
    d0 = ndimage.distance_transform_edt(~bank0) * px
    m0, _ = wt.land_parts(water[dates[0]], valid[dates[0]], px)
    slab10 = _rasterize({"features": hsites["features"][:10]}, prof)
    comparable = [d for d in dates[1:] if q0 and qd.get(d) and max(q0, qd[d]) / min(q0, qd[d]) < STAGE_RATIO]
    ret_rows = []
    for i, f in enumerate(hsites["features"][:10], 1):
        site = (slab10 == i) & m0
        series = []
        for d in dates[1:]:
            sel = site & water[d]
            series.append({"date": d, "retreat_m": round(float(d0[sel].max())) if sel.any() else 0, "comparable_flow": d in comparable})
        pts = [(0, 0.0)] + [((_d(s["date"]) - _d(dates[0])).days, s["retreat_m"]) for s in series if s["comparable_flow"]]
        rate = round(float(np.polyfit([p[0] for p in pts], [p[1] for p in pts], 1)[0]), 2) if len(pts) >= 3 else None
        ret_rows.append({"site_id": f["properties"]["site_id"], "union": f["properties"].get("union"), "area_ha": f["properties"]["area_ha"],
                         "lat": f["properties"]["lat"], "lon": f["properties"]["lon"], "series": series, "rate_m_per_day": rate})
    rates = [r for r in ret_rows if r["rate_m_per_day"] is not None]
    fast = max(rates, key=lambda r: r["rate_m_per_day"]) if rates else None
    ret_sec = {"sites": ret_rows, "comparable_passes": comparable,
               "rate_rule": "least-squares slope of retreat vs days over 18 Jun plus passes with flow within 1.3x of 18 Jun",
               "takeaway": (f"Fastest retreat among the top sites: {fast['site_id']} ({fast['union']}) at about {fast['rate_m_per_day']:.1f} m/day "
                            f"over passes with comparable flow.") if fast else None}
    _csv(idir / "site_retreat.csv", [{"site_id": r["site_id"], "rate_m_per_day": r["rate_m_per_day"],
                                      **{s["date"]: s["retreat_m"] for s in r["series"]}} for r in ret_rows])

    # 7. what we learned (only from numbers above; unreliable ones are left out)
    learned = ([river_sec["takeaway"]] if river_sec["reliable"] else []) + [freq_sec["takeaway"]]
    for t in (bl_take, where_sec["takeaway"], near_sec["takeaway"], ret_sec["takeaway"]):
        if t:
            learned.append(t)
    out = {"aoi": aoi, "track": TRACK, "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
           "river": river_sec, "frequency": freq_sec, "bankloss_time": bl_sec, "where": where_sec, "near_bank": near_sec,
           "retreat": ret_sec, "learned": learned,
           "csv": sorted(p.name for p in idir.glob("*.csv"))}
    (idir / "insights.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    for s_ in learned:
        print("[insights]", s_)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--aoi", default="kazipur")
    run(ap.parse_args().aoi)
