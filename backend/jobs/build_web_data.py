"""Build the static data the web app serves from its CDN (frontend/public/data/). Copies and resizes only.

  python -m jobs.build_web_data --science <kit outputs/kazipur> --radar-rule <outputs/kazipur/radar_rule>

Writes:
  ov/*.png|webp       map pictures, long side <= 2048 px (masks as palette PNG, imagery as WebP)
  geo/*.geojson       bank-loss sites, banklines, river channel, unions (coordinates rounded to ~10 m, simplified)
  season.json         every NISAR pass over the reach (NASA CMR record), what each processed pass shows,
                      river flow and rain per day, the radar gap
  story.json          the headline numbers, each with the file it comes from
  unions.json         per-union numbers for the explorer table
  validation.json     skill table (stage proxy, persistence, ML) and HH vs HV contrast
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path
from typing import Any

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT.parent / "frontend" / "public" / "data"
DATA = ROOT / "data"
LONG = 2048
Image.MAX_IMAGE_PIXELS = None


# ---------------------------------------------------------------- pictures
def _fit(im: Image.Image, long: int = LONG) -> Image.Image:
    w, h = im.size
    k = long / max(w, h)
    return im if k >= 1 else im.resize((round(w * k), round(h * k)), Image.LANCZOS)


def mask_png(src: Path, dst: Path, colors: int = 8) -> None:
    im = _fit(Image.open(src).convert("RGBA"))
    q = im.quantize(colors=colors, method=Image.Quantize.FASTOCTREE)
    dst.parent.mkdir(parents=True, exist_ok=True)
    q.save(dst, optimize=True)


def webp(src: Path, dst: Path, quality: int = 72, long: int = LONG) -> None:
    im = _fit(Image.open(src).convert("RGBA"), long)
    dst.parent.mkdir(parents=True, exist_ok=True)
    im.save(dst, "WEBP", quality=quality, method=6)


# ---------------------------------------------------------------- geometry
def _rdp(pts: list[list[float]], eps: float) -> list[list[float]]:
    if len(pts) < 3:
        return pts
    (x1, y1), (x2, y2) = pts[0][:2], pts[-1][:2]
    dx, dy = x2 - x1, y2 - y1
    n = (dx * dx + dy * dy) ** 0.5 or 1e-12
    dmax, idx = 0.0, 0
    for i in range(1, len(pts) - 1):
        d = abs(dy * pts[i][0] - dx * pts[i][1] + x2 * y1 - y2 * x1) / n
        if d > dmax:
            dmax, idx = d, i
    if dmax > eps:
        return _rdp(pts[: idx + 1], eps)[:-1] + _rdp(pts[idx:], eps)
    return [pts[0], pts[-1]]


def _geom(g: dict[str, Any], eps: float, nd: int) -> dict[str, Any] | None:
    def ring(r: list[list[float]], closed: bool) -> list[list[float]] | None:
        pts = [p[:2] for p in r]
        if closed and len(pts) > 4:
            # a closed ring starts and ends on the same point: split it at the vertex farthest from the start
            x0, y0 = pts[0]
            k = max(range(len(pts)), key=lambda i: (pts[i][0] - x0) ** 2 + (pts[i][1] - y0) ** 2)
            simp = _rdp(pts[: k + 1], eps)[:-1] + _rdp(pts[k:], eps)
        else:
            simp = _rdp(pts, eps)
        r2 = [[round(p[0], nd), round(p[1], nd)] for p in simp]
        if closed and len(r2) < 4:
            return None
        return r2
    t = g["type"]
    if t == "Polygon":
        rings = [x for x in (ring(r, True) for r in g["coordinates"]) if x]
        return {"type": t, "coordinates": rings} if rings else None
    if t == "MultiPolygon":
        polys = [[x for x in (ring(r, True) for r in poly) if x] for poly in g["coordinates"]]
        polys = [p for p in polys if p]
        return {"type": t, "coordinates": polys} if polys else None
    if t == "LineString":
        return {"type": t, "coordinates": ring(g["coordinates"], False)}
    if t == "MultiLineString":
        return {"type": t, "coordinates": [ring(r, False) for r in g["coordinates"]]}
    if t == "Point":
        return {"type": t, "coordinates": [round(c, 6) for c in g["coordinates"]]}
    return g


def slim_geojson(src: Path, dst: Path, eps: float = 0.00012, nd: int = 5, keep: list[str] | None = None) -> int:
    fc = json.loads(src.read_text(encoding="utf-8"))
    out = []
    for f in fc["features"]:
        g = _geom(f["geometry"], eps, nd) if f.get("geometry") else None
        if g is None:
            continue
        props = f.get("properties") or {}
        if keep is not None:
            props = {k: props.get(k) for k in keep if k in props}
        out.append({"type": "Feature", "geometry": g, "properties": props})
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps({"type": "FeatureCollection", "features": out}, separators=(",", ":")), encoding="utf-8")
    return len(out)


def _csv(p: Path) -> list[dict[str, str]]:
    with open(p, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _num(x: Any) -> float | None:
    try:
        return None if x in (None, "") else float(x)
    except ValueError:
        return None


# ---------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--science", required=True, type=Path)
    ap.add_argument("--radar-rule", required=True, type=Path)
    ap.add_argument("--unions", type=Path)
    a = ap.parse_args()
    sci, rr_dir = a.science, a.radar_rule
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "ov").mkdir(parents=True)

    summary = json.loads((sci / "summary.json").read_text(encoding="utf-8"))
    insights = json.loads((sci / "insights" / "insights.json").read_text(encoding="utf-8"))
    overlays = json.loads((sci / "overlays.json").read_text(encoding="utf-8"))
    rr = json.loads((rr_dir / "index.json").read_text(encoding="utf-8"))
    bounds = overlays[0]["bounds"]

    # pictures ------------------------------------------------------------
    pics: dict[str, Any] = {"bounds": bounds, "water": {}, "newwater": {}, "sar": {}, "optical": {}, "bankloss": {}, "other": {}}
    for o in overlays:
        if o.get("group") == "water_date":
            date, track = o["id"].split("_")[1:3]
            mask_png(sci / o["url"], OUT / "ov" / f"water_{date}_{track}.png", 4)
            pics["water"][f"{track}_{date}"] = f"ov/water_{date}_{track}.png"
        elif o.get("group") == "sar_grey":
            date, track = o["label"].split()[1:3]
            key = f"{track}_{date}"
            if key not in pics["sar"]:
                webp(sci / o["url"], OUT / "ov" / f"sar_{date}_{track}.webp", 70)
                pics["sar"][key] = f"ov/sar_{date}_{track}.webp"
    for p in rr["passes"]:
        if p.get("overlay"):
            name = f"newwater_{p['track']}_{p['date']}.png"
            mask_png(rr_dir / Path(p["overlay"]["url"]).name, OUT / "ov" / name, 4)
            pics["newwater"][f"{p['track']}_{p['date']}"] = f"ov/{name}"
    for name, label in (("scene_L89_20260509", "Landsat 8/9, 9 May 2026 (before the monsoon)"),
                        ("scene_S2_20261015", "Sentinel-2, 15 Oct 2026 (after the monsoon)"),
                        ("scene_L89_20261016", "Landsat 8/9, 16 Oct 2026")):
        if (sci / "overlays" / f"{name}.webp").exists():
            webp(sci / "overlays" / f"{name}.webp", OUT / "ov" / f"{name}.webp", 74)
            pics["optical"][name] = {"url": f"ov/{name}.webp", "label": label}
    for pair in ("erosion_069A_interim", "erosion_069A", "erosion_019D"):
        f = sci / "overlays" / f"{pair}_eroded.png"
        if f.exists():
            mask_png(f, OUT / "ov" / f"bankloss_{pair}.png", 4)
            pics["bankloss"][pair] = f"ov/bankloss_{pair}.png"
    for src, name in ((sci / "overlays" / "river_khal.png", "river_khal.png"),
                      (sci / "insights" / "times_under_water.png", "times_under_water.png"),
                      (sci / "overlays" / "hand.png", "hand.png"),
                      (sci / "overlays" / "erosion_069A_interim_char_change.png", "char_change_069A_interim.png")):
        if src.exists():
            mask_png(src, OUT / "ov" / name, 16 if name in ("times_under_water.png", "hand.png") else 6)
            pics["other"][name.split(".")[0]] = f"ov/{name}"

    # geometry -------------------------------------------------------------
    head = "erosion_069A_interim"
    geo = {}
    geo["sites"] = slim_geojson(sci / "pairs" / f"{head}_sites.geojson", OUT / "geo" / "sites.geojson", 0.00005, 5,
                                ["site_id", "area_ha", "max_retreat_m", "building_count", "union", "upazila", "lat", "lon",
                                 "land_cover", "confirmed", "mean_coherence"])
    geo["banklines"] = slim_geojson(sci / "pairs" / f"{head}_banklines.geojson", OUT / "geo" / "banklines.geojson", 0.00008, 5)
    geo["river"] = slim_geojson(sci / "river_khal.geojson", OUT / "geo" / "river.geojson", 0.0002, 4, [])
    if a.unions and a.unions.exists():
        geo["unions"] = slim_geojson(a.unions, OUT / "geo" / "unions.geojson", 0.00025, 4, ["shapeID", "shapeName"])

    # season -------------------------------------------------------------
    cmr = json.loads((DATA / "passes.json").read_text(encoding="utf-8"))
    granules = cmr.get("granules") or cmr.get("passes") or []
    rr_by = {f"{p['track']}_{p['date']}": p for p in rr["passes"]}
    water_by = {r["date"]: r for r in insights["river"]["passes"]}
    processed = []
    for key, p in sorted(rr_by.items(), key=lambda kv: kv[1]["acquired_utc"]):
        w = water_by.get(p["date"]) if p["track"] == "069A" else None
        processed.append({
            "key": key, "track": p["track"], "date": p["date"], "acquired_utc": p["acquired_utc"],
            "published_utc": p.get("published_utc"), "granule_id": p.get("granule_id"), "cmr_id": p.get("cmr_id"),
            "processing_level": p.get("processing_level"), "is_baseline": p.get("is_baseline", False),
            "threshold_db": p.get("threshold_db"), "new_water_km2": p.get("new_water_km2") or None,
            "range_within_25pct": p.get("range_within_25pct"), "unknown_pct": p.get("unknown_pct"),
            "water_km2": None if w is None else w["water_km2"],
            "water_outside_channel_km2": None if w is None else w["water_outside_channel_km2"],
            "discharge_m3s": None if w is None else w["discharge_m3s"],
            "water_png": pics["water"].get(key), "newwater_png": pics["newwater"].get(key), "sar_webp": pics["sar"].get(key),
        })
    rain = {r["date"]: _num(r["mm"]) for r in _csv(DATA / "rain_daily.csv")}
    daily = [{"date": d["date"], "discharge_m3s": d.get("discharge_m3s"), "rain_power_mm": d.get("rain_mm"),
              "rain_imerg_mm": rain.get(f"{d['date'][:4]}-{d['date'][4:6]}-{d['date'][6:]}")}
             for d in insights["river"]["daily"]]
    season = {
        "aoi": {"id": "kazipur", "label": summary.get("label"), "bbox": summary.get("bbox"), "grid_m": summary.get("grid_m")},
        "gap_utc": summary.get("radar_gap") or ["2026-07-27T22:03:25Z", "2026-08-10T00:55:27Z"],
        "cmr": {"retrieved_utc": cmr["meta"].get("retrieved_utc"), "granules": granules},
        "processed": processed, "daily": daily, "pictures": pics,
        "thresholds_by_track": summary.get("thresholds_by_track"),
        "fit": insights["river"].get("fit"), "fit_takeaway": insights["river"].get("takeaway"),
        "sources": {"daily_discharge": "GloFAS v4 (Copernicus EMS) through Open-Meteo, modelled river flow",
                    "rain_power_mm": "NASA POWER PRECTOTCORR at the reach centre",
                    "rain_imerg_mm": "NASA IMERG V07 Early daily, wettest cell in the reach (NASA SERVIR ClimateSERV)"},
    }
    (OUT / "season.json").write_text(json.dumps(season, separators=(",", ":")), encoding="utf-8")

    # story -------------------------------------------------------------
    pairs = summary["pairs"]
    hp = pairs[head]
    story = {
        "generated_from": "13 Nov 2026 kit outputs (summary.json, insights.json) and jobs.j1 radar-rule index",
        "headline_pair": {k: hp.get(k) for k in ("id", "track", "before", "after", "confirm_pass", "mainland_bank_loss_ha_range",
                                                 "mainland_bank_loss_ha_mid", "bank_loss_confirmed", "new_water_km2_range",
                                                 "threshold", "caveat", "exposure", "sites_count", "dates") if k in hp},
        "pairs": {k: {kk: v.get(kk) for kk in ("track", "before", "after", "confirm_pass", "mainland_bank_loss_ha_range",
                                                "bank_loss_confirmed", "new_water_km2_range", "flooded_vegetation_km2_range")}
                  for k, v in pairs.items()},
        "insights": {k: insights.get(k) for k in ("frequency", "bankloss_time", "where", "near_bank", "retreat", "learned")},
        "river_fit": insights["river"].get("fit"),
        "latest_processed": summary.get("latest_pass"),
        "file": {"pairs": f"pairs/{head}.json", "insights": "insights/insights.json"},
    }
    (OUT / "story.json").write_text(json.dumps(story, separators=(",", ":")), encoding="utf-8")

    # unions -------------------------------------------------------------
    us = json.loads((sci / "union_summary.json").read_text(encoding="utf-8"))
    bn = json.loads((DATA / "union_names_bn.json").read_text(encoding="utf-8"))
    near = {r["union"]: r for r in insights["near_bank"]["by_union"]}
    where = {r["union"]: r for r in insights["where"]["rows"]}
    rows = []
    for u in us:
        o = u.get("nisar_observation") or {}
        c = u.get("coordinates") or {}
        name = u.get("union_name_en")
        rows.append({"union_id": u.get("union_id"), "name_en": name, "name_bn": bn.get(name), "upazila": u.get("upazila_name_en"),
                     "lat": c.get("lat"), "lon": c.get("lon"),
                     "new_water_km2_range": o.get("new_water_km2_range"),
                     "bank_loss_ha_range": o.get("mainland_bank_loss_ha_range"),
                     "bank_loss_confirmed": o.get("bank_loss_confirmed"),
                     "flooded_vegetation_km2_range": o.get("flooded_vegetation_km2_range"),
                     "buildings_within_100m_of_retreating_bank": (near.get(name) or {}).get("buildings_100m"),
                     "buildings_within_500m_of_retreating_bank": (near.get(name) or {}).get("buildings_500m"),
                     "bank_loss_sites": (where.get(name) or {}).get("sites"),
                     "cropland_lost_ha": (where.get(name) or {}).get("cropland_ha"),
                     "buildings_on_lost_land": (where.get(name) or {}).get("buildings")})
    (OUT / "unions.json").write_text(json.dumps(rows, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")

    # validation -------------------------------------------------------------
    val = json.loads((DATA / "persistence_and_polarisation_test.json").read_text(encoding="utf-8"))
    fc = sci / "forecast" / "forecast.json"
    if fc.exists():           # the three-row skill table: stage proxy, ML (leave one pass out), persistence
        import statistics as st
        lopo = json.loads(fc.read_text(encoding="utf-8"))["ml_challenger"]["lopo"]["with_prev"]
        pers = {p["pass"]: p for p in val["persistence"]}
        rows_s = [{"pass": r["pass_date"], "stage_proxy": r["baseline"]["csi"], "ml": r["ml"]["csi"],
                   "persistence": (pers.get(r["pass_date"]) or {}).get("csi")} for r in lopo]
        mean = lambda k: round(st.mean([x[k] for x in rows_s if x[k] is not None]), 3)  # noqa: E731
        val["skill"] = {"rows": rows_s, "mean": {k: mean(k) for k in ("stage_proxy", "ml", "persistence")},
                        "persistence_wins": sum(1 for x in rows_s if x["persistence"] is not None and x["persistence"] > x["ml"]),
                        "n": len(rows_s),
                        "metric": "CSI (critical success index) on water outside the permanent channel, each pass predicted without seeing it",
                        "sources": {"stage_proxy": "forecast.json ml_challenger.lopo baseline", "ml": "forecast.json ml_challenger.lopo with_prev",
                                    "persistence": "data/persistence_and_polarisation_test.json (previous pass of the same track)"}}
    (OUT / "validation.json").write_text(json.dumps(val, separators=(",", ":")), encoding="utf-8")
    shutil.copy(DATA / "stations.json", OUT / "stations.json")
    shutil.copy(DATA / "gibs_layers.json", OUT / "gibs_layers.json")

    total = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file())
    big = sorted(((f.stat().st_size, f.name) for f in OUT.rglob("*") if f.is_file()), reverse=True)[:5]
    print(f"[build_web_data] {OUT}: {total / 1e6:.1f} MB; geo {geo}; largest {[(n, round(s / 1e3)) for s, n in big]}")


if __name__ == "__main__":
    main()
