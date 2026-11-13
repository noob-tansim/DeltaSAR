"""Build the small data folder the deployed API needs (baked into the Docker image).

  python -m jobs.build_backend_data --science <kit outputs/kazipur> --radar-rule <outputs/kazipur/radar_rule> \
         --unions <cache/vector/unions.geojson>

Reads the full-resolution kit outputs and writes `deploy_data/kazipur/`:
  radar_rule/index.json + dist_*.tif     distance to new water per pass, 40 m, uint16 metres (min of 2x2 cells,
                                          so a distance is never made longer than at 20 m)
  layers/river_mask.tif, hand_m.tif, dist_river_m.tif   40 m
  union_summary.json, summary.json, timeline.json
  demo_households.json                   real union centre points used by the guided demo, with their real
                                          distance to new water at the 24 Jul 2026 pass

Nothing is computed that the kit did not compute; this only resamples and copies.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import transform as warp_xy

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "deploy_data" / "kazipur"
FACTOR = 2   # 20 m -> 40 m


def _blocks(a: np.ndarray, how: str) -> np.ndarray:
    h, w = a.shape[0] // FACTOR * FACTOR, a.shape[1] // FACTOR * FACTOR
    b = a[:h, :w].reshape(h // FACTOR, FACTOR, w // FACTOR, FACTOR).swapaxes(1, 2).reshape(h // FACTOR, w // FACTOR, -1)
    if how == "min":
        return np.nanmin(b, axis=2) if b.dtype.kind == "f" else b.min(axis=2)
    if how == "mean":
        return np.nanmean(b, axis=2)
    if how == "max_valid":          # river mask: 1 if any valid cell is river; 255 (nodata) only if all are nodata
        valid = np.where(b == 255, 0, b)
        out = valid.max(axis=2)
        out[(b == 255).all(axis=2)] = 255
        return out
    raise ValueError(how)


def resample(src_path: Path, dst_path: Path, how: str, dtype: str | None = None) -> None:
    import warnings
    with rasterio.open(src_path) as src:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)       # all-NaN blocks stay NaN
            data = _blocks(src.read(1), how)
        h, w = data.shape
        transform = src.transform * src.transform.scale(FACTOR, FACTOR)
        prof = src.profile.copy()
        prof.update(height=h, width=w, transform=transform, compress="deflate", predictor=2 if data.dtype.kind in "ui" else 3,
                    tiled=True, blockxsize=256, blockysize=256)
        if dtype:
            prof["dtype"] = dtype
            data = data.astype(dtype)
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(dst_path, "w", **prof) as dst:
            dst.write(data, 1)


def sample(path: Path, lat: float, lon: float) -> float | None:
    with rasterio.open(path) as src:
        xs, ys = warp_xy("EPSG:4326", src.crs, [lon], [lat])
        r, c = src.index(xs[0], ys[0])
        if not (0 <= r < src.height and 0 <= c < src.width):
            return None
        v = float(src.read(1, window=((r, r + 1), (c, c + 1)))[0, 0])
        if src.nodata is not None and (v == src.nodata or np.isnan(v)):
            return None
        return v


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--science", required=True, type=Path, help="kit outputs/kazipur (13 Nov kit)")
    ap.add_argument("--radar-rule", required=True, type=Path, help="outputs/kazipur/radar_rule written by jobs.j1")
    ap.add_argument("--unions", type=Path, help="cache/vector/unions.geojson (geoBoundaries ADM4 clipped)")
    a = ap.parse_args()

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "radar_rule").mkdir(parents=True)

    idx = json.loads((a.radar_rule / "index.json").read_text(encoding="utf-8"))
    idx["grid"] = {**idx.get("grid", {}), "pixel_m": 20 * FACTOR, "note": "resampled from 20 m with the minimum of each 2x2 block"}
    for p in idx["passes"]:
        for name in (p.get("files") or {}).values():
            resample(a.radar_rule / name, OUT / "radar_rule" / name, "min")
    (OUT / "radar_rule" / "index.json").write_text(json.dumps(idx, indent=1), encoding="utf-8")

    layers = a.science / "layers"
    resample(layers / "river_mask.tif", OUT / "layers" / "river_mask.tif", "max_valid")
    resample(layers / "hand_m.tif", OUT / "layers" / "hand_m.tif", "mean")
    resample(layers / "dist_river_m.tif", OUT / "layers" / "dist_river_m.tif", "min")

    for f in ("union_summary.json", "summary.json", "timeline.json"):
        shutil.copy(a.science / f, OUT / f)

    # Demo households: union centre points, ranked by their real distance to new water on the 24 Jul pass.
    rr = next(p for p in idx["passes"] if p["date"] == "20260724" and p["track"] == "069A")
    unions = json.loads((a.science / "union_summary.json").read_text(encoding="utf-8"))
    rows = []
    for u in unions:
        c = u.get("coordinates") or {}
        if c.get("lat") is None:
            continue
        lat, lon = c["lat"], c["lon"]
        if sample(OUT / "layers" / "river_mask.tif", lat, lon) == 1.0:
            continue
        d_mid = sample(OUT / "radar_rule" / rr["files"]["mid"], lat, lon)
        d_strict = sample(OUT / "radar_rule" / rr["files"]["strict"], lat, lon)
        if d_mid is None or d_mid >= 65535:
            continue
        rows.append({"union_id": u["union_id"], "union": u.get("union_name_en"), "upazila": u.get("upazila_name_en"),
                     "lat": lat, "lon": lon, "d_mid_m": int(d_mid),
                     "d_strict_m": None if d_strict is None or d_strict >= 65535 else int(d_strict)})
    rows.sort(key=lambda r: r["d_mid_m"])
    # The visitor's own phone: a place where new water is a few hundred metres away at T and also at T-1 dB ("sure").
    sure = [r for r in rows if 250 <= r["d_mid_m"] <= 900 and r["d_strict_m"] is not None and r["d_strict_m"] <= 1000]
    less = [r for r in rows if 150 <= r["d_mid_m"] <= 1000 and (r["d_strict_m"] is None or r["d_strict_m"] > 1000)]
    inside = [r for r in rows if 60 <= r["d_mid_m"] < 250]
    watch = [r for r in rows if 1050 <= r["d_mid_m"] <= 2000]
    far = sorted(rows, key=lambda r: -r["d_mid_m"])
    visitor = next((r for r in sure if r["union"] == "Char Girish"), sure[0] if sure else rows[0])
    pick: list[dict] = []
    for r in [*sure[:2], *less[:1], *inside[:1], *watch[:1], *far[:1]]:
        if r is not visitor and r not in pick:
            pick.append(r)
    (OUT / "demo_households.json").write_text(json.dumps({
        "_note": "Real union centre points (geoBoundaries) and their real distance to new water on the NISAR 24 Jul "
                 "2026 pass (069A, threshold T and T-1 dB). Households are demo participants placed there, not residents.",
        "pass": "069A_20260724", "visitor": visitor, "households": pick, "all_ranked": rows}, indent=1), encoding="utf-8")
    print(f"[build_backend_data] visitor phone at {visitor['union']} ({visitor['d_mid_m']} m, strict {visitor['d_strict_m']} m)")

    total = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file())
    print(f"[build_backend_data] wrote {OUT} ({total / 1e6:.1f} MB); demo households: "
          + ", ".join(f"{r['union']} {r['d_mid_m']} m" for r in pick))


if __name__ == "__main__":
    main()
