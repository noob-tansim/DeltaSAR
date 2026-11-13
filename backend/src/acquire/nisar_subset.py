"""Cut the AOI out of a NISAR L2 GCOV granule and save HHHH/HVHV as GeoTIFF (dB) + a receipt.

Works on Windows/Mac/Linux with only h5py + rasterio. h5py reads just the AOI window,
so a 6-9 GB file never has to fit in RAM.

  # what's inside a file
  python -m src.acquire.nisar_subset inspect  D:/nisar/NISAR_L2_PR_GCOV_..._001.h5

  # one local file (e.g. from the team Drive)
  python -m src.acquire.nisar_subset cut  D:/nisar/NISAR_L2_PR_GCOV_..._001.h5

  # stream straight from ASF, no 6 GB download (needs `pip install earthaccess` + Earthdata Login)
  python -m src.acquire.nisar_subset cut-dates --inventory NISAR_Jamuna_granule_inventory.csv --dates 20260618 20260724 20261016

Output (cache/sar/<aoi>/):
  nisar_<YYYYMMDD>_<track><A|D>_HHHH_db.tif, ..._HVHV_db.tif, ..._receipt.json
"""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
import re

import h5py
import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds

from src.config import AOIS, CRS, FULL_TRACKS, aoi_dir

GRID = "/science/LSAR/GCOV/grids/frequencyA"
NAME_RE = re.compile(r"NISAR_L2_(?P<lvl>\w\w)_GCOV_(?P<cycle>\d{3})_(?P<track>\d{3})_(?P<dir>[AD])_(?P<frame>\d{3})_"
                     r"(?P<mode>\d{4})_(?P<pol>\w{4})_\w_(?P<start>\d{8}T\d{6})_(?P<stop>\d{8}T\d{6})_(?P<crid>\w+?)_")
DB_MIN, DB_MAX = -35.0, 5.0   # team contract: outside this range = "unknown"


def parse_name(name: str) -> dict:
    m = NAME_RE.search(name)
    if not m:
        raise SystemExit(f"Not a NISAR GCOV granule name: {name}")
    d = m.groupdict()
    d["track_id"] = f"{d['track']}{d['dir']}"
    d["date"] = d["start"][:8]
    d["granule"] = pathlib.Path(name).stem
    return d


def inspect(src) -> None:
    with h5py.File(src, "r") as f:
        def show(name, obj):
            if isinstance(obj, h5py.Dataset) and ("GCOV/grids" in name or "identification" in name):
                print(f"{name:75s} {obj.shape} {obj.dtype}")
        f.visititems(show)


def to_db(linear: np.ndarray) -> np.ndarray:
    """gamma0 (linear power) -> dB. Zero/fill/out-of-range -> NaN ('unknown')."""
    lin = np.where(np.isfinite(linear) & (linear > 0), linear, np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        db = 10.0 * np.log10(lin)
    return np.where((db >= DB_MIN) & (db <= DB_MAX), db, np.nan).astype("float32")


def _georef(g):
    x, y = g["xCoordinates"][()], g["yCoordinates"][()]
    proj = g["projection"]
    epsg = proj.attrs.get("epsg_code", None)
    epsg = int(np.asarray(proj[()] if epsg is None else epsg).item())
    return x, y, epsg


def cut(src, name: str, aoi: str = "kazipur", pols=("HHHH", "HVHV"), cmr_id: str | None = None,
        url: str | None = None) -> list[str]:
    meta = parse_name(name)
    if meta["track_id"] not in FULL_TRACKS:
        print(f"[nisar] WARNING track {meta['track_id']} does not fully cover the AOI; not used for change maps")
    w, s, e, n = AOIS[aoi]["bbox"]
    written = []
    with h5py.File(src, "r") as f:
        g = f[GRID]
        x, y, epsg = _georef(g)
        xmin, ymin, xmax, ymax = transform_bounds("EPSG:4326", f"EPSG:{epsg}", w, s, e, n)
        cols = np.where((x >= xmin) & (x <= xmax))[0]
        rows = np.where((y >= ymin) & (y <= ymax))[0]
        if cols.size == 0 or rows.size == 0:
            raise SystemExit(f"AOI not inside {meta['granule']} (EPSG:{epsg})")
        c0, c1, r0, r1 = cols.min(), cols.max() + 1, rows.min(), rows.max() + 1
        dx, dy = float(x[1] - x[0]), float(y[1] - y[0])
        transform = from_origin(x[c0] - dx / 2, y[r0] - dy / 2, dx, -dy)
        stem = f"nisar_{meta['date']}_{meta['track_id']}"
        stats = {}
        for pol in pols:
            if pol not in g:
                print(f"[nisar] {pol} not in file, skipping")
                continue
            db = to_db(g[pol][r0:r1, c0:c1].astype("float32"))   # reads only this window
            out = aoi_dir(aoi, "sar") / f"{stem}_{pol}_db.tif"
            with rasterio.open(out, "w", driver="GTiff", height=db.shape[0], width=db.shape[1], count=1,
                               dtype="float32", crs=f"EPSG:{epsg}", transform=transform, nodata=np.nan,
                               compress="deflate", tiled=True) as dst:
                dst.write(db, 1)
            stats[pol] = {"unknown_pct": round(float(np.isnan(db).mean() * 100), 1),
                          "median_db": round(float(np.nanmedian(db)), 2)}
            print(f"[nisar] {out.name} {db.shape} {abs(dx):.0f} m  unknown {stats[pol]['unknown_pct']}%  "
                  f"median {stats[pol]['median_db']} dB")
            written.append(str(out))
    receipt = {
        "granule_id": meta["granule"], "cmr_id": cmr_id, "source_url": url,
        "acquired_utc": f"{meta['start'][:4]}-{meta['start'][4:6]}-{meta['start'][6:8]}T"
                        f"{meta['start'][9:11]}:{meta['start'][11:13]}:{meta['start'][13:15]}Z",
        "track": meta["track_id"], "frame": meta["frame"], "mode": meta["mode"], "polarization": meta["pol"],
        "processing_level": f"L2 GCOV {'PROVISIONAL' if meta['lvl'] == 'PR' else meta['lvl']} (CRID {meta['crid']})",
        "native_crs": f"EPSG:{epsg}", "pixel_m": abs(dx), "analysis_crs": CRS,
        "valid_range_db": [DB_MIN, DB_MAX], "stats": stats,
    }
    (aoi_dir(aoi, "sar") / f"{stem}_receipt.json").write_text(json.dumps(receipt, indent=1))
    return written


def cut_dates(inventory: str, dates: list[str], aoi: str = "kazipur"):
    """Stream selected full-track GCOV granules from ASF using the team's inventory CSV."""
    import earthaccess  # pip install earthaccess
    rows = [r for r in csv.DictReader(open(inventory, encoding="utf-8"))
            if r["collection"].startswith("NISAR_L2_GCOV") and r["date"].replace("-", "") in dates
            and f"{r['track']}{r['direction'][0]}" in FULL_TRACKS]
    if not rows:
        raise SystemExit("No full-track GCOV rows for those dates in the inventory")
    earthaccess.login()   # asks for Earthdata username/password once, or uses ~/.netrc
    for r in rows:
        print(f"[nisar] streaming {r['granule']} ({r['size_MB']} MB on disk, reading AOI only)")
        fobj = earthaccess.open([r["h5_url"]])[0]
        cut(fobj, r["granule"], aoi, cmr_id=r["cmr_id"], url=r["h5_url"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("inspect"); a.add_argument("h5")
    b = sub.add_parser("cut"); b.add_argument("h5"); b.add_argument("--aoi", default="kazipur")
    b.add_argument("--cmr-id", default=None)
    c = sub.add_parser("cut-dates"); c.add_argument("--inventory", required=True)
    c.add_argument("--dates", nargs="+", required=True); c.add_argument("--aoi", default="kazipur")
    args = ap.parse_args()
    if args.cmd == "inspect":
        inspect(args.h5)
    elif args.cmd == "cut":
        cut(args.h5, pathlib.Path(args.h5).name, args.aoi, cmr_id=args.cmr_id)
    else:
        cut_dates(args.inventory, args.dates, args.aoi)
