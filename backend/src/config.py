"""Shared settings: paths, the AOI grid, NISAR tracks and the change pairs.

The AOI is the team's Sirajganj-Kazipur reach of the Jamuna, defined directly in
UTM 45N metres (EPSG:32645) so every layer lands on the same analysis grid.
"""
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]

# local, git-ignored settings (e.g. EE_PROJECT=...) in ROOT/.env; real environment variables win
import os as _os
if (ROOT / ".env").exists():
    for _ln in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in _ln and not _ln.lstrip().startswith("#"):
            _k, _v = _ln.split("=", 1)
            _os.environ.setdefault(_k.strip(), _v.strip())
CACHE = ROOT / "cache"
FIXTURES = ROOT / "demo_fixtures"
# DELTASAR_OUTPUTS lets re-runs and dry runs write elsewhere (then src/pipeline/publish.py swaps atomically),
# so the live server never reads half-written files
OUTPUTS = pathlib.Path(_os.environ.get("DELTASAR_OUTPUTS", ROOT / "outputs"))
VECTOR = CACHE / "vector"

CRS = "EPSG:32645"

AOIS = {
    "kazipur": {
        "label": "Sirajganj-Kazipur reach (Jamuna)",
        "utm_extent": (750000, 2680000, 795000, 2745000),   # xmin, ymin, xmax, ymax (m)
        "bbox": (89.46, 24.205, 89.918, 24.80),             # lon/lat, approx, for weather + API lookup
        "grid_m": 20,   # 20 m: track 019D mixes 10 m (4005) and 20 m (2005); 069A 10 m is averaged to 20 m
    },
}

# Only these two NISAR tracks cover 100% of the AOI (team data audit, 3 Nov 2026).
# 170A clips the AOI, 091D barely touches it: never use them for change maps.
FULL_TRACKS = {"069A", "019D"}

# Permanent NISAR instrument gap (ASF). Shown as "no radar data", never filled by a model.
NISAR_GAP_UTC = ("2026-07-27T22:03:25Z", "2026-08-10T00:55:27Z")

# Change rules (src/compute/water.py)
WATER_SPECK_HA = 2.0              # water bodies smaller than this are ignored when finding mainland / chars
BANK_LOSS_MAX_RETREAT_M = 1500    # mainland bank loss only within this distance of the before bankline
FV_HH_MIN_DB = -8.0               # flooded vegetation: HH_after above this (double bounce) ...
FV_HH_HV_MIN_DB = 6.0             # ... and HH_after - HV_after above this ...
FV_HH_RISE_MIN_DB = 3.0           # ... and HH rose by at least this since the before pass

# Same-track change pairs (UTC acquisition dates). Plan B = the first two.
PAIRS = [
    {"id": "erosion_069A", "track": "069A", "before": "20260618", "after": "20261016",
     "story": "Bank erosion / char change, pre- vs post-monsoon"},
    {"id": "rise_069A", "track": "069A", "before": "20260618", "after": "20260724",
     "story": "Monsoon rise before the 27 Jul radar gap"},
    {"id": "erosion_019D", "track": "019D", "before": "20260627", "after": "20261013",
     "story": "Erosion cross-check on the descending track"},
    # Interim pairs from the passes already on disk (11 Nov 2026). Keep until the pairs above have their data.
    {"id": "erosion_069A_interim", "track": "069A", "before": "20260618", "after": "20261004",
     "story": "INTERIM bank erosion / char change, Jun 18 vs Oct 4 (16 Oct confirms it when present)"},
    {"id": "rise_069A_interim", "track": "069A", "before": "20260618", "after": "20260910",
     "story": "INTERIM monsoon water, Jun 18 vs Sep 10 (12 Jul copy incomplete, 17 Aug not on disk yet)"},
]


def aoi_dir(aoi: str, kind: str) -> pathlib.Path:
    """cache/<kind>/<aoi>/ , created on demand. kind = sar | dem"""
    p = CACHE / kind / aoi
    p.mkdir(parents=True, exist_ok=True)
    return p


def out_dir(aoi: str) -> pathlib.Path:
    p = OUTPUTS / aoi
    (p / "overlays").mkdir(parents=True, exist_ok=True)
    (p / "layers").mkdir(parents=True, exist_ok=True)
    return p


def base_profile(aoi: str) -> dict:
    """The analysis grid every layer is resampled onto."""
    from rasterio.transform import from_origin
    xmin, ymin, xmax, ymax = AOIS[aoi]["utm_extent"]
    px = AOIS[aoi]["grid_m"]
    w, h = int(round((xmax - xmin) / px)), int(round((ymax - ymin) / px))
    return {"driver": "GTiff", "crs": CRS, "transform": from_origin(xmin, ymax, px, px),
            "width": w, "height": h, "count": 1}
