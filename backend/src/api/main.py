"""Reference API + map (Plan A). Under Plan B the same files in outputs/ are served statically.

  uvicorn src.api.main:app --reload --port 8000
  http://127.0.0.1:8000/        map with before/after swipe
  http://127.0.0.1:8000/docs    API docs
"""
from __future__ import annotations

import json
import os
import threading
import time

import requests
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from src.config import AOIS, OUTPUTS, ROOT
from src.pipeline.run_aoi import location_status

app = FastAPI(title="DeltaSAR SAR + DEM layers")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
OUTPUTS.mkdir(exist_ok=True)
(ROOT / "web" / "tiles").mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=OUTPUTS), name="outputs")
app.mount("/tiles", StaticFiles(directory=ROOT / "web" / "tiles"), name="tiles")
app.mount("/vendor", StaticFiles(directory=ROOT / "web" / "vendor"), name="vendor")   # MapLibre served locally (offline)


def _aoi_for(lat, lon):
    for k, v in AOIS.items():
        w, s, e, n = v["bbox"]
        if w <= lon <= e and s <= lat <= n:
            return k
    return None


def _json(path):
    if not path.exists():
        raise HTTPException(404, f"{path.name} not built yet: run python -m src.pipeline.run_aoi")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/v1/aois")
def aois():
    return [{"id": k, "label": v["label"], "bbox": v["bbox"], "ready": (OUTPUTS / k / "summary.json").exists()}
            for k, v in AOIS.items()]


@app.get("/api/v1/aoi/{aoi}/summary")
def summary(aoi: str):
    return _json(OUTPUTS / aoi / "summary.json")


@app.get("/api/v1/aoi/{aoi}/unions")
def unions(aoi: str):
    return _json(OUTPUTS / aoi / "union_summary.json")


@app.get("/api/v1/aoi/{aoi}/overlays")
def overlays(aoi: str):
    items = _json(OUTPUTS / aoi / "overlays.json")
    for o in items:
        o["url"] = f"/outputs/{aoi}/{o['url']}"
    return items


@app.get("/api/v1/aoi/{aoi}/pairs/{pair}")
def pair(aoi: str, pair: str):
    return _json(OUTPUTS / aoi / "pairs" / f"{pair}.json")


@app.get("/api/v1/aoi/{aoi}/pairs/{pair}/sites")
def pair_sites(aoi: str, pair: str, kind: str = Query("mainland", pattern="^(mainland|char)$")):
    """Mainland bank-loss sites (S01.., largest first) or char land lost (C01..) as GeoJSON."""
    return _json(OUTPUTS / aoi / "pairs" / (f"{pair}_sites.geojson" if kind == "mainland" else f"{pair}_char_sites.geojson"))


@app.get("/api/v1/aoi/{aoi}/pairs/{pair}/buildings")
def pair_buildings(aoi: str, pair: str):
    p = OUTPUTS / aoi / "pairs" / f"{pair}_buildings.geojson"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"type": "FeatureCollection", "features": []}


@app.get("/api/v1/aoi/{aoi}/insights")
def insights(aoi: str):
    """Statistics behind the map (src/compute/insights.py); CSVs under /outputs/<aoi>/insights/."""
    return _json(OUTPUTS / aoi / "insights" / "insights.json")


@app.get("/api/v1/aoi/{aoi}/timeline")
def timeline(aoi: str):
    """Observed passes per track, expected passes (12-day cadence), forecast window."""
    return _json(OUTPUTS / aoi / "timeline.json")


@app.get("/api/v1/aoi/{aoi}/forecast")
def forecast(aoi: str):
    fc = _json(OUTPUTS / aoi / "forecast" / "forecast.json")
    for d in fc.get("days", []):
        d["overlay"]["url"] = f"/outputs/{aoi}/{d['overlay']['url']}"
    return fc


_COMPARE_LOCK = threading.Lock()


@app.get("/api/v1/aoi/{aoi}/compare")
def compare_dates(aoi: str, track: str, before: str, after: str, confirm: str | None = None):
    """Bank loss between two observed passes of ONE track (cached under outputs/<aoi>/pairs/custom_*)."""
    from src.compute.compare import compare
    with _COMPARE_LOCK:
        try:
            return compare(aoi, track, before, after, confirm)
        except ValueError as exc:
            raise HTTPException(400, str(exc))


_INGEST = {"state": "idle", "started": None, "finished": None, "result": None, "error": None}


def _run_ingest(aoi):
    from src.pipeline import ingest_new
    try:
        r = ingest_new.run(aoi)
        _INGEST.update(state="done", result={k: r.get(k) for k in ("new_passes", "remote_found", "remote_error", "seconds")})
    except Exception as exc:
        _INGEST.update(state="error", error=repr(exc))
    _INGEST["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")


@app.post("/api/v1/aoi/{aoi}/ingest")
def ingest(aoi: str, request: Request):
    """Check the Track folders and ASF for new radar passes (localhost only); runs in a background thread."""
    if request.client and request.client.host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(403, "ingest is allowed from localhost only")
    if _INGEST["state"] == "running":
        return _INGEST
    _INGEST.update(state="running", started=time.strftime("%Y-%m-%dT%H:%M:%S"), finished=None, result=None, error=None)
    threading.Thread(target=_run_ingest, args=(aoi,), daemon=True).start()
    return _INGEST


@app.get("/api/v1/aoi/{aoi}/ingest")
def ingest_status(aoi: str):
    return _INGEST


_ESRI_TILEMAP = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tilemap"


@app.get("/api/v1/aoi/{aoi}/esri-maxzoom")
def esri_maxzoom(aoi: str):
    """Deepest Esri World Imagery level really available at every bank-loss site centroid (probed once, cached)."""
    import math
    cache = ROOT / "cache" / "api" / f"esri_maxzoom_{aoi}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    pts = []
    for p in sorted((OUTPUTS / aoi / "pairs").glob("erosion_*_sites.geojson"))[:1]:
        pts = [(f["properties"]["lat"], f["properties"]["lon"]) for f in json.loads(p.read_text())["features"][:12]]
    if not pts or os.getenv("OFFLINE") == "1":
        return {"maxzoom": 17, "checked": 0, "note": "not probed (offline or no sites); default 17"}

    def avail(z, lat, lon):
        n = 2 ** z; x = int((lon + 180) / 360 * n)
        y = int((1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n)
        r = requests.get(f"{_ESRI_TILEMAP}/{z}/{y}/{x}/1/1", params={"f": "json"}, timeout=20).json()
        return bool(r.get("data", [0])[0])
    best = 17
    try:
        for z in (18, 19, 20):
            if all(avail(z, la, lo) for la, lo in pts):
                best = z
            else:
                break
    except Exception as exc:
        return {"maxzoom": 17, "checked": 0, "note": f"probe failed ({exc!r}); default 17"}
    out = {"maxzoom": best, "checked": len(pts), "method": "Esri MapServer tilemap at site centroids"}
    cache.write_text(json.dumps(out))
    return out


@app.get("/api/v1/map-config")
def map_config():
    return {"offline": os.getenv("OFFLINE") == "1", "google_satellite": bool(os.getenv("GOOGLE_MAPS_KEY"))}


@app.get("/api/v1/google-tiles")
def google_tiles():
    """Official Google Map Tiles API session (only when GOOGLE_MAPS_KEY is set; billed to that key's project)."""
    key = os.getenv("GOOGLE_MAPS_KEY")
    if not key:
        raise HTTPException(404, "GOOGLE_MAPS_KEY not set")
    r = requests.post(f"https://tile.googleapis.com/v1/createSession?key={key}",
                      json={"mapType": "satellite", "language": "en-US", "region": "BD"}, timeout=30)
    if not r.ok:
        raise HTTPException(502, f"Map Tiles API createSession failed: HTTP {r.status_code}")
    s = r.json()["session"]
    return {"tiles": [f"https://tile.googleapis.com/v1/2dtiles/{{z}}/{{x}}/{{y}}?session={s}&key={key}"],
            "attribution": "Map data © Google", "maxzoom": 20}


@app.get("/api/v1/gibs-cache")
def gibs_cache():
    p = ROOT / "web" / "tiles" / "index.json"
    return json.loads(p.read_text()) if p.exists() else {}


@app.get("/api/v1/location-status")
def location(lat: float = Query(..., ge=20, le=27), lon: float = Query(..., ge=88, le=93)):
    aoi = _aoi_for(lat, lon)
    if aoi is None or not (OUTPUTS / aoi / "summary.json").exists():
        return {"coordinates": {"lat": lat, "lon": lon}, "covered": False,
                "message": "Outside the processed area (Sirajganj-Kazipur reach)."}
    return {"covered": True, **location_status(aoi, lat, lon)}


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@app.get("/")
def index():
    return FileResponse(ROOT / "web" / "index.html")
