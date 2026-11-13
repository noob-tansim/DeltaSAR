"""Challenger for the PREDICTIVE water layer: a statistical model trained on NISAR water masks.

  python -m src.compute.water_ml --aoi kazipur        # leave-one-pass-out evaluation + fit + save

"Is this pixel open water on date d?" scikit-learn HistGradientBoostingClassifier, CPU, fixed seed.
Features per pixel and date:
  static : height above river (HAND raster in use), distance to the river mask, DEM, WorldCover class (categorical)
  driver : GloFAS discharge on d, 5- and 10-day means, 5-day trend
  rain   : antecedent rain 3 / 7 / 15-day sums (NASA POWER; Open-Meteo for the last days and the forecast;
           POWER 2-year daily mean beyond the 16-day weather forecast)
  state  : wet at the previous pass of the track, days since that pass  (variant "no_prev" drops these two)
Sampling: per pass a stratified (class-proportional) sample of SAMPLE_PER_PASS pixels, permanent river excluded.
Validation: leave-one-PASS-out only (pixels of one date never split across train/test), plus a hindcast
(predict the newest pass from the passes before it). Compared with the deterministic stage-proxy baseline on the
same evaluation pixels. No generative AI is involved; this is a trained statistical classifier.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import platform

import numpy as np
from rasterio.warp import Resampling
from scipy import ndimage

from src.acquire.safe import fetch_json
from src.compute import water as wt
from src.config import AOIS, CACHE, aoi_dir, base_profile, out_dir

SEED = 0
SAMPLE_PER_PASS = 250_000
EVAL_PER_PASS = 400_000
LABEL = "statistical model trained on NISAR water masks (HistGradientBoosting), PREDICTIVE, experimental"
FEATS_STATIC = ["hand_m", "dist_river_m", "dem_m", "worldcover"]
FEATS_DYN = ["q", "q_mean5", "q_mean10", "q_trend5", "rain3", "rain7", "rain15"]
FEATS_STATE = ["prev_wet", "days_since_prev"]


def _d(s):
    return dt.date(int(s[:4]), int(s[4:6]), int(s[6:]))


def rain_series(aoi):
    """{yyyymmdd: mm} from NASA POWER (2 years), then Open-Meteo past 30 / next 16 days; plus the climatology."""
    w, s, e, n = AOIS[aoi]["bbox"]; la, lo = round((s + n) / 2 * 4) / 4, round((w + e) / 2 * 4) / 4
    end = dt.date.today() - dt.timedelta(days=7); start = end - dt.timedelta(days=730)
    power, _ = fetch_json("https://power.larc.nasa.gov/api/temporal/daily/point",
                          {"parameters": "PRECTOTCORR", "community": "AG", "latitude": la, "longitude": lo,
                           "start": start.strftime("%Y%m%d"), "end": end.strftime("%Y%m%d"), "format": "JSON"},
                          name=f"power_{la:.2f}_{lo:.2f}", timeout=60)
    ser = {k: max(0.0, float(v)) for k, v in power["properties"]["parameter"]["PRECTOTCORR"].items() if v is not None and v >= 0}
    clim = float(np.mean(list(ser.values()))) if ser else 5.0
    met, _ = fetch_json("https://api.open-meteo.com/v1/forecast",
                        {"latitude": la, "longitude": lo, "daily": "precipitation_sum", "timezone": "Asia/Dhaka",
                         "past_days": 30, "forecast_days": 16}, name=f"meteo30_{la:.2f}_{lo:.2f}", timeout=60)
    for t, v in zip(met["daily"]["time"], met["daily"]["precipitation_sum"]):
        k = t.replace("-", "")
        if k not in ser and v is not None:
            ser[k] = float(v)
    return ser, clim


def dyn_features(date, Q, rain, clim):
    qd = dict(zip(Q["time"], Q["q_median"]))
    def q(k):
        v = qd.get((_d(date) - dt.timedelta(days=k)).strftime("%Y%m%d"))
        return float(v) if v is not None and np.isfinite(v) else np.nan
    qs = [q(k) for k in range(0, 10)]
    r = lambda n: sum(rain.get((_d(date) - dt.timedelta(days=k)).strftime("%Y%m%d"), clim) for k in range(n))  # noqa: E731
    return {"q": qs[0], "q_mean5": float(np.nanmean(qs[:5])), "q_mean10": float(np.nanmean(qs)),
            "q_trend5": qs[0] - qs[4] if np.isfinite(qs[4]) else 0.0, "rain3": r(3), "rain7": r(7), "rain15": r(15)}


def static_stack(aoi, prof, river):
    from src.compute.exposure import worldcover
    from src.pipeline.run_aoi import to_grid
    d = aoi_dir(aoi, "dem"); px = prof["transform"].a
    hand = to_grid(d / "hand.tif", prof, Resampling.bilinear)
    dem = to_grid(d / "dem.tif", prof, Resampling.bilinear) if (d / "dem.tif").exists() else np.full(hand.shape, np.nan, "float32")
    dist = (ndimage.distance_transform_edt(~river) * px).astype("float32")
    wc = worldcover(aoi, prof)
    wc = np.zeros(hand.shape, "uint8") if wc is None else wc
    return {"hand_m": hand, "dist_river_m": dist, "dem_m": dem, "worldcover": wc.astype("float32")}


def build_X(static, idx, dyn, prev=None, days_since=None, use_state=True):
    cols = [static[k].ravel()[idx] for k in FEATS_STATIC]
    cols += [np.full(idx.size, dyn[k], "float32") for k in FEATS_DYN]
    if use_state:
        cols += [prev.ravel()[idx].astype("float32"), np.full(idx.size, float(days_since), "float32")]
    return np.column_stack(cols).astype("float32")


def _sample(rng, eligible, y, n):
    """Class-proportional sample of flat indices."""
    pos = np.flatnonzero(eligible & y); neg = np.flatnonzero(eligible & ~y)
    tot = pos.size + neg.size
    npos = int(round(n * pos.size / max(tot, 1))); nneg = n - npos
    return np.concatenate([rng.choice(pos, min(npos, pos.size), replace=False), rng.choice(neg, min(nneg, neg.size), replace=False)])


def _scores(p, y, cut=0.5):
    yes = p >= cut
    tp, fp, fn = int((yes & y).sum()), int((yes & ~y).sum()), int((~yes & y).sum())
    f = float(y.mean()); brier = float(np.mean((p - y) ** 2))
    return {"csi": round(tp / max(tp + fp + fn, 1), 3), "hit_rate": round(tp / max(tp + fn, 1), 3),
            "false_alarm_ratio": round(fp / max(tp + fp, 1), 3),
            "area_error_pct": round(100 * ((tp + fp) - (tp + fn)) / max(tp + fn, 1), 1),
            "brier": round(brier, 4), "brier_skill_score": round(1 - brier / (f * (1 - f)), 3) if 0 < f < 1 else None}


def model():
    from sklearn.ensemble import HistGradientBoostingClassifier
    return HistGradientBoostingClassifier(max_iter=200, learning_rate=0.08, max_leaf_nodes=31, l2_regularization=1.0,
                                          categorical_features=[3], random_state=SEED)


def evaluate(aoi="kazipur", track="069A", cl=None, baseline_h=None, Q=None) -> dict:
    """Leave-one-pass-out + hindcast for the ML challenger (with and without previous state) vs the baseline."""
    import joblib
    import sklearn
    from src.pipeline.run_aoi import list_passes, load_pass, to_grid
    prof = base_profile(aoi); px = AOIS[aoi]["grid_m"]; od = out_dir(aoi)
    river = to_grid(aoi_dir(aoi, "dem") / "river_mask.tif", prof, Resampling.nearest) >= 0.5
    thr = json.loads((od / "summary.json").read_text())["thresholds_by_track"][track]["threshold_db"]
    passes = [p for p in list_passes(aoi) if p["track"] == track]
    static = static_stack(aoi, prof, river)
    rain, clim = rain_series(aoi)
    rng = np.random.default_rng(SEED)
    obs, elig, dyn = {}, {}, {}
    for p in passes:
        lp = load_pass(p, prof)
        obs[p["date"]] = wt.classify(lp["hh"], lp["hv"], thr, px)["open_water"]
        elig[p["date"]] = np.isfinite(lp["hh"]) & np.isfinite(static["hand_m"]) & ~river
        dyn[p["date"]] = dyn_features(p["date"], Q, rain, clim)
    dates = [p["date"] for p in passes]
    prev_of = {d: dates[i - 1] for i, d in enumerate(dates) if i > 0}
    samples, evals = {}, {}
    for d in dates:
        samples[d] = _sample(rng, elig[d], obs[d], SAMPLE_PER_PASS)
        evals[d] = _sample(np.random.default_rng(SEED + 1), elig[d], obs[d], EVAL_PER_PASS)

    def XY(d, idx, use_state):
        pv = prev_of.get(d)
        X = build_X(static, idx, dyn[d], obs[pv] if pv else None, (_d(d) - _d(pv)).days if pv else None, use_state)
        return X, obs[d].ravel()[idx]

    res = {"with_prev": [], "no_prev": []}
    for variant, use_state in (("with_prev", True), ("no_prev", False)):
        dd = [d for d in dates if (d in prev_of or not use_state)]
        for k in dd:
            train = [d for d in dd if d != k]
            X = np.concatenate([XY(d, samples[d], use_state)[0] for d in train]); y = np.concatenate([XY(d, samples[d], use_state)[1] for d in train])
            m = model().fit(X, y)
            Xe, ye = XY(k, evals[k], use_state)
            pr = m.predict_proba(Xe)[:, 1]
            row = {"pass_date": k, "ml": _scores(pr, ye)}
            if cl is not None and baseline_h is not None and k in baseline_h:
                bw = (cl.ravel()[evals[k]] <= baseline_h[k] + 1e-6).astype(float)
                row["baseline"] = _scores(bw, ye)
            res[variant].append(row)
            print(f"[ml] LOPO {variant} {k}: ML CSI {row['ml']['csi']} BSS {row['ml']['brier_skill_score']}"
                  + (f" | baseline CSI {row['baseline']['csi']}" if "baseline" in row else ""))
    # hindcast: newest pass from all earlier passes (with previous state = the pass before it)
    newest = dates[-1]
    train = [d for d in dates[:-1] if d in prev_of]
    X = np.concatenate([XY(d, samples[d], True)[0] for d in train]); y = np.concatenate([XY(d, samples[d], True)[1] for d in train])
    mh = model().fit(X, y)
    Xe, ye = XY(newest, evals[newest], True)
    hind = {"predict": newest, "trained_on": train, "ml": _scores(mh.predict_proba(Xe)[:, 1], ye)}
    # wins: with_prev variant vs baseline, by CSI
    wins = sum(1 for r in res["with_prev"] if "baseline" in r and r["ml"]["csi"] > r["baseline"]["csi"])
    n = sum(1 for r in res["with_prev"] if "baseline" in r)
    # final model on all passes (with state) for forecasting
    train = [d for d in dates if d in prev_of]
    X = np.concatenate([XY(d, samples[d], True)[0] for d in train]); y = np.concatenate([XY(d, samples[d], True)[1] for d in train])
    final = model().fit(X, y)
    path = CACHE / f"water_ml_{aoi}_{track}.joblib"
    joblib.dump(final, path)
    out = {"label": LABEL, "track": track, "features": FEATS_STATIC + FEATS_DYN + FEATS_STATE, "seed": SEED,
           "sample_per_pass": SAMPLE_PER_PASS, "eval_per_pass": EVAL_PER_PASS, "training_passes": train,
           "versions": {"python": platform.python_version(), "scikit-learn": sklearn.__version__, "numpy": np.__version__},
           "lopo": res, "hindcast": hind, "ml_wins_vs_baseline": f"{wins}/{n}", "use_ml": n > 0 and wins > n / 2,
           "model_file": str(path), "evaluated_on": "pixels outside the permanent river mask, class-proportional sample",
           "decision_rule": "ML is used for the PREDICTIVE layer only if its leave-one-pass-out CSI beats the baseline on most passes"}
    (CACHE / f"water_ml_{aoi}_{track}_receipt.json").write_text(json.dumps(out, indent=1))
    out["_ctx"] = {"static": static, "obs": obs, "dates": dates, "rain": rain, "clim": clim, "river": river, "model": final}
    return out


def predict_day(ctx, date, Q, last_date):
    """Probability map for a forecast day: previous state = last observed pass, days-since increasing."""
    static, river = ctx["static"], ctx["river"]
    elig = np.isfinite(static["hand_m"]) & ~river
    idx = np.flatnonzero(elig)
    dyn = dyn_features(date, Q, ctx["rain"], ctx["clim"])
    X = build_X(static, idx, dyn, ctx["obs"][last_date], (_d(date) - _d(last_date)).days, True)
    p = np.zeros(river.shape, "float32"); p.ravel()[idx] = ctx["model"].predict_proba(X)[:, 1]
    return p


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--aoi", default="kazipur")
    from src.compute.forecast import glofas
    a = ap.parse_args()
    r = evaluate(a.aoi, Q=glofas(a.aoi, (dt.date.today() + dt.timedelta(days=30)).isoformat()))
    r.pop("_ctx"); print(json.dumps({k: r[k] for k in ("ml_wins_vs_baseline", "use_ml", "hindcast")}, indent=1))
