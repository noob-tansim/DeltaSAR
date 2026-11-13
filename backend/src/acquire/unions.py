"""Union (ADM4) and upazila (ADM3) boundaries for the AOI from geoBoundaries (CC BY 3.0 IGO). Not GADM.

  python -m src.acquire.unions --aoi kazipur

Writes cache/vector/unions.geojson (unions intersecting the AOI bbox, properties shapeID, shapeName, upazila)
and cache/vector/unions_receipt.json. The raw national files are cached under cache/vector/raw/.
"""
from __future__ import annotations

import argparse
import json

import requests
from rasterio import features
from rasterio.warp import transform_geom

from src.config import AOIS, VECTOR

API = "https://www.geoboundaries.org/api/current/gbOpen/BGD/{lvl}/"


def _get(lvl):
    meta = requests.get(API.format(lvl=lvl), timeout=60).json()
    raw = VECTOR / "raw"; raw.mkdir(parents=True, exist_ok=True)
    p = raw / f"geoBoundaries-BGD-{lvl}.geojson"
    if not p.exists():
        r = requests.get(meta["gjDownloadURL"], timeout=600); r.raise_for_status()
        p.write_bytes(r.content)
    return json.loads(p.read_text(encoding="utf-8")), meta


def _bbox(geom):
    xs, ys = [], []
    def walk(c):
        if isinstance(c[0], (int, float)):
            xs.append(c[0]); ys.append(c[1])
        else:
            for x in c:
                walk(x)
    walk(geom["coordinates"])
    return min(xs), min(ys), max(xs), max(ys)


def _inside(pt, geom):
    """Point in (multi)polygon, even-odd on all rings."""
    x, y = pt
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    c = False
    for poly in polys:
        for ring in poly:
            for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
                if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                    c = not c
    return c


def _centroid(geom):
    pts = []
    def walk(c):
        if isinstance(c[0], (int, float)):
            pts.append(c)
        else:
            for x in c:
                walk(x)
    walk(geom["coordinates"])
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def run(aoi="kazipur"):
    w, s, e, n = AOIS[aoi]["bbox"]
    adm4, m4 = _get("ADM4")
    adm3, m3 = _get("ADM3")
    keep = []
    for f in adm4["features"]:
        x0, y0, x1, y1 = _bbox(f["geometry"])
        if x1 < w or x0 > e or y1 < s or y0 > n:
            continue
        keep.append(f)
    ups = [(u, _bbox(u["geometry"])) for u in adm3["features"]]
    for f in keep:
        c = _centroid(f["geometry"])
        up = next((u for u, b in ups if b[0] <= c[0] <= b[2] and b[1] <= c[1] <= b[3] and _inside(c, u["geometry"])), None)
        p = f["properties"]
        f["properties"] = {"shapeID": p.get("shapeID"), "shapeName": p.get("shapeName"),
                           "upazila": up["properties"].get("shapeName") if up else None}
    (VECTOR / "unions.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": keep}), encoding="utf-8")
    rc = {"source": "geoBoundaries gbOpen BGD ADM4 (unions) + ADM3 (upazilas)", "licence": m4.get("boundaryLicense"),
          "boundary_source": m4.get("boundarySource"), "year": m4.get("boundaryYearRepresented"),
          "urls": [m4["gjDownloadURL"], m3["gjDownloadURL"]], "unions_in_bbox": len(keep),
          "attribution": "geoBoundaries (Runfola et al. 2020), CC BY 3.0 IGO"}
    (VECTOR / "unions_receipt.json").write_text(json.dumps(rc, indent=1))
    print(f"[unions] {len(keep)} unions intersect the AOI bbox -> {VECTOR / 'unions.geojson'}")
    return rc


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--aoi", default="kazipur")
    run(ap.parse_args().aoi)
