"""The deployed API (Render): alert layer, guided-demo sandboxes, point reports. The web app lives on Vercel.

  uvicorn src.api.app:app --port 8000          (local)
  http://127.0.0.1:8000/docs                   every route, generated from the code

The kit's analyst server (src/api/main.py) is unchanged and still runs locally for the science team.
"""
from __future__ import annotations

import datetime as dt
import os
import threading
import time
from typing import Any

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from sqlalchemy import func, select, text

from src.alerts import engine, inputs, lifecycle, sandbox, settings
from src.alerts.db import RainDaily, RiverReading, init_engine, session_scope, utcnow
from src.alerts.types import DHAKA, in_aoi
from src.api import alerts_routes, ask_routes, sandbox_routes, tts_routes

VERSION = os.environ.get("RENDER_GIT_COMMIT", engine.code_version())[:7]
LIVE_INPUTS = os.environ.get("LIVE_INPUTS", "1") == "1" and os.environ.get("OFFLINE") != "1"
REFRESH_INPUTS_S = int(os.environ.get("REFRESH_INPUTS_S", 6 * 3600))

app = FastAPI(
    title="DeltaSAR · বন্যা সাথী API",
    version=VERSION,
    description="NISAR radar evidence → fixed rules → volunteer approval → spoken alert → counted reply. "
                "Not an official warning. Official forecasts: FFWC, BMD, call 1090.",
)
_origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_origin_regex=os.environ.get("ALLOWED_ORIGIN_REGEX") or None,
                   allow_methods=["*"], allow_headers=["*"])
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.include_router(alerts_routes.router)
app.include_router(alerts_routes.console)
app.include_router(sandbox_routes.router)
app.include_router(ask_routes.router)
app.include_router(tts_routes.router)

_STATE: dict[str, Any] = {"started_utc": utcnow(), "last_round_utc": None, "last_inputs_refresh_utc": None,
                          "last_inputs_result": None}


@app.get("/", include_in_schema=False)
def root() -> dict[str, Any]:
    return {"service": "DeltaSAR · Bonna Sathi API", "docs": "/docs", "health": "/api/v1/health"}


@app.get("/api/v1/health", tags=["service"])
def health() -> dict[str, Any]:
    """Used by the web app ("waking the server") and by the keep-warm ping."""
    db_ok = True
    rain_days = river_rows = 0
    try:
        with session_scope() as s:
            s.execute(text("select 1"))
            rain_days = int(s.scalar(select(func.count()).select_from(RainDaily)) or 0)
            river_rows = int(s.scalar(select(func.count()).select_from(RiverReading)) or 0)
    except Exception:
        db_ok = False
    passes = inputs.radar_passes()
    rasters = "ok"
    try:                                       # read one real cell, so a broken GDAL/rasterio shows up here
        inputs.sample_raster(settings.AOI_OUT / "layers" / "river_mask.tif", 24.5, 89.69)
    except Exception as exc:
        rasters = f"error: {type(exc).__name__}: {exc}"[:200]
    return {"ok": db_ok and bool(passes) and rasters == "ok", "version": VERSION, "db": "ok" if db_ok else "error",
            "rasters": rasters,
            "database": "postgres" if settings.database_url().startswith("postgresql") else "sqlite",
            "radar_passes": len(passes), "newest_pass": passes[-1].key if passes else None,
            "rain_days": rain_days, "river_readings": river_rows, "started_utc": _STATE["started_utc"],
            "last_round_utc": _STATE["last_round_utc"], "last_inputs_refresh_utc": _STATE["last_inputs_refresh_utc"],
            "last_inputs_result": _STATE["last_inputs_result"]}


@app.get("/api/v1/point", tags=["map"])
def point(lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180)) -> dict[str, Any]:
    """What the radar saw at one point: height above the river, distance to the river, and the distance to new water
    at every NISAR pass (water that was land at the track's baseline pass). Point samples, 40 m cells."""
    if not in_aoi(lat, lon):
        return {"covered": False, "lat": lat, "lon": lon, "message": "Outside the processed reach (Sirajganj-Kazipur, Jamuna)."}
    layers = settings.AOI_OUT / "layers"
    in_river = inputs.sample_raster(layers / "river_mask.tif", lat, lon) == 1.0
    hand = inputs.sample_raster(layers / "hand_m.tif", lat, lon)
    d_river = inputs.sample_raster(layers / "dist_river_m.tif", lat, lon)
    us = inputs.unions()
    near = min(us, key=lambda u: (u["lat"] - lat) ** 2 + (u["lon"] - lon) ** 2) if us else None
    series = []
    for p in inputs.radar_passes():
        if p.is_baseline:
            series.append({"key": p.key, "track": p.track, "date": p.date, "baseline": True})
            continue
        d = {k: inputs._dist(p, k, lat, lon) for k in ("strict", "mid", "loose")}
        series.append({"key": p.key, "track": p.track, "date": p.date, "baseline": False,
                       "acquired_utc": p.acquired_utc, "processing_level": p.processing_level,
                       "dist_new_water_m": {k: None if v is None else int(round(v)) for k, v in d.items()}})
    return {
        "covered": True, "lat": lat, "lon": lon, "in_permanent_river": in_river,
        "height_above_river_m": None if hand is None else round(hand, 1),
        "distance_to_river_m": None if d_river is None else int(round(d_river)),
        "nearest_union": None if near is None else {k: near[k] for k in ("union_id", "name_en", "name_bn", "upazila_en", "lat", "lon")},
        "passes": series,
        "notes": ["Distance to new water: metres from this point to the nearest pixel that was land at the baseline "
                  "pass of the same track and water at this pass (T = track threshold; strict T-1 dB, loose T+1 dB).",
                  "Height above river: MERIT Hydro HAND (about 90 m, errors of a metre or more). Not a depth.",
                  "Observation, not a forecast. Not an official warning."],
    }


# ---------------------------------------------------------------- background work
def _refresh_inputs() -> None:
    """Newest IMERG rain (NASA SERVIR ClimateSERV) and FFWC river readings; the CSV snapshots if a source is down."""
    from jobs import j2_load_inputs as j2
    result = {}
    for name, fn in (("rain", j2.load_rain), ("river", j2.load_river)):
        try:
            result[name] = f"live, {fn(False)} new"
        except Exception as exc:
            try:
                result[name] = f"snapshot ({type(exc).__name__}), {fn(True)} new"
            except Exception as exc2:
                result[name] = f"failed: {exc2!r}"[:200]
    _STATE["last_inputs_refresh_utc"], _STATE["last_inputs_result"] = utcnow(), result


def _loop() -> None:
    last_refresh = 0.0
    while True:
        try:
            with session_scope() as s:
                engine.tick(s)
            with session_scope() as s, engine.LOCK:
                lifecycle.sweep(s)
            with session_scope() as s:
                sandbox.purge_expired(s)
            _STATE["last_round_utc"] = utcnow()
        except Exception as exc:
            print(f"[alerts] background round failed: {exc!r}")
        if LIVE_INPUTS and time.time() - last_refresh > REFRESH_INPUTS_S:
            last_refresh = time.time()
            threading.Thread(target=_refresh_inputs, daemon=True, name="inputs-refresh").start()
        time.sleep(max(settings.TICK_S, 5))


@app.on_event("startup")
def _startup() -> None:
    init_engine()
    from jobs import j2_load_inputs as j2
    with session_scope() as s:
        empty = not s.scalar(select(func.count()).select_from(RainDaily))
    if empty:                                   # first start on a new database: load the snapshots in data/
        j2.load_rain(True)
        j2.load_river(True)
    from jobs.seed_demo import seed
    seed()
    if settings.TICK_S > 0:
        threading.Thread(target=_loop, daemon=True, name="alerts-loop").start()
    print(f"[api] started {dt.datetime.now(DHAKA):%Y-%m-%d %H:%M} Dhaka; version {VERSION}; "
          f"{len(inputs.radar_passes())} radar passes; db {settings.database_url().split('://')[0]}")
