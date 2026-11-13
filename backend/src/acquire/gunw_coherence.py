"""InSAR coherence between consecutive passes, from NISAR L2 GUNW files (20 m wrapped-interferogram coherence).

  python -m src.acquire.gunw_coherence --aoi kazipur

Reads only the AOI window of /science/LSAR/GUNW/grids/frequencyA/wrappedInterferogram/HH/coherenceMagnitude
from every GUNW .h5 in Data/Track69 and Data/Track19 and writes cache/coherence/<aoi>/coh_<track>_<d1>_<d2>.tif
(float32 0..1, native UTM) + a receipt. Low coherence = the surface changed between the two passes
(bank collapse, new water, but also water surfaces, crops growing, flooding): an observation layer only,
never used by the prediction or the bank-loss rules.
"""
from __future__ import annotations

import argparse
import json
import re

import h5py
import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds

from src.config import AOIS, CACHE, ROOT

BASE = "/science/LSAR/GUNW/grids/frequencyA/wrappedInterferogram"
NAME = re.compile(r"NISAR_L2_\w\w_GUNW_\d{3}_(\d{3})_([AD])_.*?_(\d{8})T\d{6}_\d{8}T\d{6}_(\d{8})T")


def run(aoi="kazipur"):
    w, s, e, n = AOIS[aoi]["bbox"]
    od = CACHE / "coherence" / aoi; od.mkdir(parents=True, exist_ok=True)
    done = []
    for sub in ("Track69", "Track19"):
        for p in sorted((ROOT / "Data" / sub).glob("*GUNW*.h5")) if (ROOT / "Data" / sub).exists() else []:
            m = NAME.search(p.name)
            if not m:
                continue
            track, d1, d2 = m.group(1) + m.group(2), m.group(3), m.group(4)
            out = od / f"coh_{track}_{d1}_{d2}.tif"
            if out.exists():
                done.append(out.name); continue
            with h5py.File(p, "r") as f:
                g = f[BASE]
                x, y = g["xCoordinates"][()], g["yCoordinates"][()]
                epsg = int(g["projection"].attrs.get("epsg_code", g["projection"][()]))
                xmin, ymin, xmax, ymax = transform_bounds("EPSG:4326", f"EPSG:{epsg}", w, s, e, n)
                cols = np.where((x >= xmin) & (x <= xmax))[0]; rows = np.where((y >= ymin) & (y <= ymax))[0]
                c0, c1, r0, r1 = cols.min(), cols.max() + 1, rows.min(), rows.max() + 1
                coh = g["HH/coherenceMagnitude"][r0:r1, c0:c1].astype("float32")
                dx, dy = float(x[1] - x[0]), float(y[1] - y[0])
            coh = np.where((coh > 0) & (coh <= 1), coh, np.nan).astype("float32")
            with rasterio.open(out, "w", driver="GTiff", height=coh.shape[0], width=coh.shape[1], count=1, dtype="float32",
                               crs=f"EPSG:{epsg}", transform=from_origin(x[c0] - dx / 2, y[r0] - dy / 2, dx, -dy),
                               nodata=np.nan, compress="deflate", tiled=True) as dst:
                dst.write(coh, 1)
            print(f"[coh] {out.name}: median {np.nanmedian(coh):.2f}, low (<0.3) {100 * np.nanmean(coh < 0.3):.0f}%")
            done.append(out.name)
    (od / "coherence_receipt.json").write_text(json.dumps({
        "source": "NISAR L2 GUNW (PROVISIONAL), wrappedInterferogram/HH/coherenceMagnitude, 20 m", "files": done,
        "meaning": "low coherence = surface changed between the two passes (also water, crops, flooding)"}, indent=1))
    return done


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--aoi", default="kazipur")
    run(ap.parse_args().aoi)
