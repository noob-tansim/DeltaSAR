"""30-day PREDICTIVE water extent, driven by river discharge (GloFAS via Open-Meteo). Deterministic, no AI.

  python -m src.compute.forecast --aoi kazipur

Model ("stage proxy"):
  1. conn_level raster: for each pixel, the lowest height level h (0..10 m, 0.1 m steps) at which it is wet when
     "wet = height-above-river <= h AND hydraulically connected (8-conn) to the river mask".
  2. For every radar pass of the forecast track, the h that best matches the SAR water mask (max CSI, pixels outside
     the permanent river mask only, so the always-wet channel does not inflate the score).
  3. h = f(Q): isotonic (PAVA) fit of h against GloFAS discharge Q on the pass dates, linear interpolation between
     points, linear extrapolation clipped to [min h, max h + 1 m].
  4. Skill: leave-one-pass-out CSI (fit without the pass, predict it) and a walk-forward replay (predict each pass
     from the passes before it only), which is what "How the prediction did at each pass" shows.
  5. Forecast for each day after the newest pass up to +30 days: h_mid = f(Q_median); band from f(Q_min) - r and
     f(Q_max) + r, with r = leave-one-out RMS height error. "likely water" = wet at h_low; "possible" = wet only at h_high.
Rain is reported as context numbers only. PREDICTIVE (experimental, not an official warning; FFWC/BMD).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json

import numpy as np
import rasterio
from rasterio.warp import Resampling
from scipy import ndimage

from src.acquire.safe import fetch_json
from src.compute import water as wt
from src.config import AOIS, aoi_dir, base_profile, out_dir

TRACK = "069A"
HORIZON_DAYS = 30
CADENCE_DAYS = 12
FIRST_PASS = "20260618"
LEVELS = np.round(np.arange(0.0, 10.01, 0.1), 2)
GLOFAS_URL = "https://flood-api.open-meteo.com/v1/flood"
GLOFAS_CANDIDATES = [(24.50, 89.70), (24.60, 89.68), (24.40, 89.68), (24.70, 89.68), (24.55, 89.66)]
LABEL = "PREDICTIVE (experimental, not an official warning; official forecasts: FFWC/BMD)"
EIGHT = np.ones((3, 3), bool)
CACHE_DIR = lambda aoi: aoi_dir(aoi, "dem")  # noqa: E731


def _d(s):
    return dt.date(int(s[:4]), int(s[4:6]), int(s[6:]))


def glofas(aoi, end: str):
    """Daily discharge at the Jamuna main-stem cell with the largest mean flow among the candidates."""
    best = None
    for lat, lon in GLOFAS_CANDIDATES:
        data, mode = fetch_json(GLOFAS_URL, {"latitude": lat, "longitude": lon,
                                "daily": "river_discharge,river_discharge_median,river_discharge_mean,river_discharge_max,river_discharge_min",
                                "start_date": "2026-06-01", "end_date": end}, name=f"glofas_{lat}_{lon}_{end}", timeout=60)
        q = np.array([np.nan if v is None else v for v in data["daily"]["river_discharge"]], float)
        if best is None or np.nanmean(q) > best[0]:
            best = (np.nanmean(q), lat, lon, data, mode)
    _, lat, lon, data, mode = best
    d = data["daily"]
    arr = lambda k: np.array([np.nan if v is None else v for v in d.get(k, [None] * len(d["time"]))], float)  # noqa: E731
    med = arr("river_discharge_median")
    med = np.where(np.isfinite(med), med, arr("river_discharge"))
    return {"time": [t.replace("-", "") for t in d["time"]], "q": arr("river_discharge"), "q_median": med,
            "q_min": arr("river_discharge_min"), "q_max": arr("river_discharge_max"),
            "query_point": [lat, lon], "cell": [data.get("latitude"), data.get("longitude")], "mode": mode,
            "source": "GloFAS v4 river discharge via Open-Meteo Flood API (flood-api.open-meteo.com/v1/flood)"}


def conn_level(hand, river):
    """Lowest level at which each pixel is wet and connected to the river (inf if never within 0..10 m)."""
    out = np.full(hand.shape, np.inf, dtype="float32")
    h = np.nan_to_num(hand, nan=1e9)
    for lv in LEVELS:
        wet = (h <= lv) | river
        lab, n = ndimage.label(wet, structure=EIGHT)
        keep = np.unique(lab[river]); keep = keep[keep > 0]
        conn = np.isin(lab, keep)
        out[conn & ~np.isfinite(out)] = lv
    return out


def csi_curve(cl, obs, evalmask):
    """TP/FP/FN for every level at once (cumulative histograms)."""
    idx = np.searchsorted(LEVELS, cl[evalmask], side="left")   # level index where the pixel turns wet (len = never)
    o = obs[evalmask]
    nl = len(LEVELS) + 1
    wet_at = np.bincount(idx, minlength=nl)[:len(LEVELS)].cumsum()
    tp_at = np.bincount(idx[o], minlength=nl)[:len(LEVELS)].cumsum()
    tot_obs = int(o.sum())
    tp = tp_at; fp = wet_at - tp_at; fn = tot_obs - tp_at
    csi = tp / np.maximum(tp + fp + fn, 1)
    return {"tp": tp, "fp": fp, "fn": fn, "csi": csi, "n_obs": tot_obs}


def score_at(curve, h):
    i = int(np.clip(np.searchsorted(LEVELS, h + 1e-9, side="right") - 1, 0, len(LEVELS) - 1))
    tp, fp, fn = int(curve["tp"][i]), int(curve["fp"][i]), int(curve["fn"][i])
    return {"csi": round(tp / max(tp + fp + fn, 1), 3), "hit_rate": round(tp / max(tp + fn, 1), 3),
            "false_alarm_ratio": round(fp / max(tp + fp, 1), 3),
            "area_error_pct": round(100 * ((tp + fp) - (tp + fn)) / max(tp + fn, 1), 1)}


def pava(x, y):
    """Isotonic (non-decreasing) regression of y on x. Returns sorted x and fitted y."""
    o = np.argsort(x, kind="stable"); xs, ys = np.asarray(x, float)[o], np.asarray(y, float)[o]
    blocks = [[v, 1.0] for v in ys]
    i = 0
    while i < len(blocks) - 1:
        if blocks[i][0] > blocks[i + 1][0]:
            v = (blocks[i][0] * blocks[i][1] + blocks[i + 1][0] * blocks[i + 1][1]) / (blocks[i][1] + blocks[i + 1][1])
            blocks[i] = [v, blocks[i][1] + blocks[i + 1][1]]; del blocks[i + 1]
            i = max(i - 1, 0)
        else:
            i += 1
    fit = np.concatenate([[v] * int(w) for v, w in blocks])
    return xs, fit


def make_f(qs, hs):
    xs, fit = pava(qs, hs)
    lo, hi = float(np.min(hs)), float(np.max(hs)) + 1.0
    def f(q):
        q = np.asarray(q, float)
        if len(xs) == 1:
            return np.clip(np.full(q.shape, fit[0]), lo, hi)
        v = np.interp(q, xs, fit)
        s_lo = (fit[1] - fit[0]) / max(xs[1] - xs[0], 1e-9); s_hi = (fit[-1] - fit[-2]) / max(xs[-1] - xs[-2], 1e-9)
        v = np.where(q < xs[0], fit[0] + s_lo * (q - xs[0]), v)
        v = np.where(q > xs[-1], fit[-1] + s_hi * (q - xs[-1]), v)
        return np.clip(v, lo, hi)
    return f, {"q": [round(float(v)) for v in xs], "h_fit": [round(float(v), 2) for v in fit]}


def rgba_classes(likely, possible):
    h, w = likely.shape
    out = np.zeros((h, w, 4), "uint8")
    out[possible] = [170, 120, 255, 150]                       # light purple: possible water
    yy, xx = np.mgrid[0:h, 0:w]
    hatch = ((xx + yy) % 6) < 2
    out[possible & hatch] = [120, 70, 220, 200]
    out[likely] = [90, 40, 200, 190]                            # deep purple-blue: likely water
    return out


def run(aoi="kazipur") -> dict:
    from src.pipeline.run_aoi import list_passes, load_pass, to_grid, write_png_4326
    prof = base_profile(aoi); px = AOIS[aoi]["grid_m"]
    dem_dir, od = aoi_dir(aoi, "dem"), out_dir(aoi)
    fd = od / "forecast"; (fd / "overlays").mkdir(parents=True, exist_ok=True)
    hand = to_grid(dem_dir / "hand.tif", prof, Resampling.bilinear)
    river = to_grid(dem_dir / "river_mask.tif", prof, Resampling.nearest) >= 0.5
    passes = [p for p in list_passes(aoi) if p["track"] == TRACK]
    if len(passes) < 3:
        raise SystemExit("need >= 3 passes on the forecast track")
    summ = json.loads((od / "summary.json").read_text())
    thr = summ["thresholds_by_track"][TRACK]["threshold_db"]
    newest = passes[-1]["date"]
    end = (_d(newest) + dt.timedelta(days=HORIZON_DAYS)).strftime("%Y-%m-%d")
    Q = glofas(aoi, end)
    qd = dict(zip(Q["time"], range(len(Q["time"]))))

    import hashlib
    ck = CACHE_DIR(aoi) / f"conn_level_{hashlib.md5(hand.tobytes()[:1 << 20] + river.tobytes()[:1 << 20]).hexdigest()[:10]}.npy"
    if ck.exists():
        cl = np.load(ck)
    else:
        cl = conn_level(hand, river); np.save(ck, cl)
    pts = []
    for p in passes:
        lp = load_pass(p, prof)
        obs = wt.classify(lp["hh"], lp["hv"], thr, px)["open_water"]
        ev = np.isfinite(lp["hh"]) & np.isfinite(hand) & ~river
        cur = csi_curve(cl, obs, ev)
        i = int(np.argmax(cur["csi"]))
        pts.append({"date": p["date"], "q": float(Q["q"][qd[p["date"]]]), "h_best": float(LEVELS[i]),
                    "csi_best": round(float(cur["csi"][i]), 3), "obs_water_km2_outside_channel": round(cur["n_obs"] * px * px / 1e6, 1),
                    "_curve": cur})
        print(f"[forecast] {p['date']}: Q {pts[-1]['q']:.0f} m3/s, best h {LEVELS[i]:.1f} m, CSI {cur['csi'][i]:.3f}")
    qs = np.array([p["q"] for p in pts]); hs = np.array([p["h_best"] for p in pts])
    f, curve = make_f(qs, hs)
    # leave-one-pass-out
    loo_res = []
    for k, p in enumerate(pts):
        m = np.arange(len(pts)) != k
        fk, _ = make_f(qs[m], hs[m])
        hk = float(fk([p["q"]])[0]); loo_res.append(hk - p["h_best"])
        p["loo"] = {"h_pred": round(hk, 2), **score_at(p["_curve"], hk)}
        p["in_sample"] = score_at(p["_curve"], float(f([p["q"]])[0]))
    r = float(np.sqrt(np.mean(np.square(loo_res))))
    # walk-forward replay: predict each pass from the passes before it (>= 3), as ingest_new does
    replay = []
    for k in range(3, len(pts)):
        fk, _ = make_f(qs[:k], hs[:k])
        hk = float(fk([pts[k]["q"]])[0])
        replay.append({"pass_date": pts[k]["date"], "fitted_on": [p["date"] for p in pts[:k]], "q": round(pts[k]["q"]),
                       "h_pred": round(hk, 2), "h_best": pts[k]["h_best"], **score_at(pts[k]["_curve"], hk)})
    # ML challenger, evaluated leave-one-pass-out on the same passes against this baseline
    ml = None
    try:
        from src.compute import water_ml
        ml = water_ml.evaluate(aoi, TRACK, cl=cl, baseline_h={p["date"]: p["loo"]["h_pred"] for p in pts}, Q=Q)
    except Exception as exc:
        print(f"[forecast] ML challenger unavailable: {exc!r}")
    use_ml = bool(ml and ml["use_ml"])
    # forecast days
    days, areas = [], []
    for j in range(1, HORIZON_DAYS + 1):
        day = (_d(newest) + dt.timedelta(days=j)).strftime("%Y%m%d")
        if day not in qd:
            continue
        i = qd[day]
        qm, qlo, qhi = Q["q_median"][i], Q["q_min"][i], Q["q_max"][i]
        if not np.isfinite(qm):
            continue
        qlo = qlo if np.isfinite(qlo) else qm; qhi = qhi if np.isfinite(qhi) else qm
        hm = float(f([qm])[0]); hl = max(0.0, float(f([qlo])[0]) - r); hh = float(f([qhi])[0]) + r
        if use_ml:
            prob = water_ml.predict_day(ml["_ctx"], day, Q, newest)
            likely = (prob >= 0.5) & ~river; mid = likely; possible = (prob >= 0.25) & ~likely & ~river
        else:
            likely = (cl <= hl + 1e-6) & ~river; mid = (cl <= hm + 1e-6) & ~river; possible = (cl <= hh + 1e-6) & ~river & ~likely
        pa = px * px / 1e6
        rec = {"date": day, "q_median": round(qm), "q_min": round(qlo), "q_max": round(qhi),
               "h_low": round(hl, 2), "h_mid": round(hm, 2), "h_high": round(hh, 2),
               "water_km2_outside_channel": {"low": round(float(likely.sum()) * pa, 1), "mid": round(float(mid.sum()) * pa, 1),
                                             "high": round(float((likely | possible).sum()) * pa, 1)},
               "river_channel_km2": round(float(river.sum()) * pa, 1)}
        b = write_png_4326(fd / "overlays" / f"forecast_{day}.png", rgba_classes(likely | river, possible), prof)
        rec["overlay"] = {"url": f"forecast/overlays/forecast_{day}.png", "bounds": b}
        days.append(rec)
    for p in pts:
        p.pop("_curve", None)
    out = {"label": LABEL, "track": TRACK, "issued_from_pass": newest, "horizon_days": HORIZON_DAYS,
           "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
           "driver": {k: Q[k] for k in ("source", "query_point", "cell", "mode")},
           "height_raster": summ["sources"].get("hand"), "water_threshold_db": thr,
           "model": {"description": "wet if height-above-river <= h(Q) and connected to the river; h(Q) isotonic in discharge",
                     "points": pts, "curve": curve, "loo_rms_height_m": round(r, 2),
                     "loo_mean_csi": round(float(np.mean([p["loo"]["csi"] for p in pts])), 3),
                     "in_sample_mean_csi": round(float(np.mean([p["in_sample"]["csi"] for p in pts])), 3),
                     "evaluated_on": "pixels outside the permanent river mask"},
           "validation_walk_forward": replay, "days": days,
           "model_used": ("ML challenger: " + water_ml.LABEL) if use_ml else
                         "deterministic stage-proxy baseline (height above river <= h(discharge))",
           "class_rule": ("likely = probability >= 0.5, possible = 0.25..0.5 (ML)" if use_ml else
                          "likely = wet at h(Q_min) - r, possible = wet only at h(Q_max) + r (baseline)"),
           "ml_challenger": None if ml is None else {k: v for k, v in ml.items() if k != "_ctx"},
           "rain_context": "local rain is not used by this layer (upstream discharge dominates on the Jamuna); see weather in summary.json"}
    (fd / "forecast.json").write_text(json.dumps(out, indent=1))
    print(f"[forecast] f(Q) points {curve}; LOO mean CSI {out['model']['loo_mean_csi']}, RMS h {r:.2f} m; "
          f"{len(days)} forecast days -> {fd}")
    write_timeline(aoi, out)
    return out


def write_timeline(aoi="kazipur", fc=None):
    """Past / present / future axis for the map: observed passes per track, expected passes, forecast window."""
    from src.pipeline.run_aoi import list_passes
    od = out_dir(aoi)
    if fc is None and (od / "forecast" / "forecast.json").exists():
        fc = json.loads((od / "forecast" / "forecast.json").read_text())
    passes = list_passes(aoi)
    tracks = {}
    for p in passes:
        tracks.setdefault(p["track"], []).append(p["date"])
    newest = max(tracks.get(TRACK, ["20260618"]))
    end = _d(newest) + dt.timedelta(days=HORIZON_DAYS)
    exp, d = [], _d(FIRST_PASS)
    while d <= end:
        s = d.strftime("%Y%m%d")
        if s not in tracks.get(TRACK, []):
            gap = "20260727" <= s <= "20260810"
            exp.append({"date": s, "status": "radar gap" if gap else ("awaiting data" if d <= dt.date.today() else "expected pass")})
        d += dt.timedelta(days=CADENCE_DAYS)
    tl = {"track": TRACK, "start": FIRST_PASS, "end": end.strftime("%Y%m%d"), "newest_observed": newest,
          "observed": {t: sorted(v) for t, v in tracks.items()}, "expected_passes": exp,
          "gap": ["20260727", "20260810"], "forecast_days": [x["date"] for x in (fc or {}).get("days", [])],
          "forecast_label": LABEL}
    (od / "timeline.json").write_text(json.dumps(tl, indent=1))
    return tl


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--aoi", default="kazipur")
    run(ap.parse_args().aoi)
