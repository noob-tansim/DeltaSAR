"""J1: layers the radar alert rule reads. Deterministic; uses the kit's own water rule and thresholds.

  python -m jobs.j1_radar_rule_layers            # all full-coverage passes
  python -m jobs.j1_radar_rule_layers --aoi kazipur --min-patch-ha 1.0

For every pass after the first (baseline) pass of its track:
  new water = open water in this pass AND land in the baseline pass, both valid, patches under --min-patch-ha dropped
  computed three times: at the track threshold T - 1 dB ("strict"), T ("mid") and T + 1 dB ("loose").
Writes to outputs/<aoi>/radar_rule/:
  dist_<track>_<date>_{strict,mid,loose}.tif   distance in metres to the nearest new water (uint16, 65535 = none)
  new_water_<track>_<date>.png                 the T mask as a map overlay (EPSG:4326)
  index.json                                   one entry per pass: receipt, areas at the three thresholds, files
Publication times come from data/passes.json (NASA CMR). A pass missing there gets acquisition + 72 h, marked "assumed".
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math

import numpy as np
from scipy import ndimage

from src.compute import water as wt
from src.config import AOIS, FULL_TRACKS, ROOT, base_profile, out_dir
from src.pipeline.run_aoi import list_passes, load_pass, mask_rgba, write_png_4326, write_tif

NODATA = 65535
LEVELS = (("strict", -1.0), ("mid", 0.0), ("loose", 1.0))


def _publication_times() -> dict[str, str]:
    p = ROOT / "data" / "passes.json"
    if not p.exists():
        return {}
    return {r["granule"]: r["published_utc"] for r in json.loads(p.read_text(encoding="utf-8"))["passes"]}


def _acquired(p: dict) -> str:
    a = p["receipt"].get("acquired_utc")
    if a:
        return a
    d = p["date"]
    return f"{d[:4]}-{d[4:6]}-{d[6:]}T00:00:00Z"


def _entry_common(p: dict, published: dict[str, str]) -> dict:
    rc = p["receipt"]
    acq = _acquired(p)
    gid = rc.get("granule_id")
    if gid in published:
        pub, src = published[gid], "NASA CMR (granule record insert time)"
    else:
        t = dt.datetime.fromisoformat(acq.replace("Z", "+00:00")) + dt.timedelta(hours=72)
        pub, src = t.strftime("%Y-%m-%dT%H:%M:%SZ"), "assumed: acquisition + 72 h (granule not in data/passes.json)"
    return {"track": p["track"], "date": p["date"], "acquired_utc": acq, "published_utc": pub,
            "publication_source": src, "granule_id": gid, "cmr_id": rc.get("cmr_id"),
            "processing_level": rc.get("processing_level") or "unknown",
            "unknown_pct": float((rc.get("stats") or {}).get("HHHH", {}).get("unknown_pct", 0.0))}


def run(aoi: str = "kazipur", min_patch_ha: float = 1.0) -> dict:
    prof = base_profile(aoi)
    px = AOIS[aoi]["grid_m"]
    od = out_dir(aoi)
    rd = od / "radar_rule"
    rd.mkdir(exist_ok=True)
    thr = json.loads((od / "summary.json").read_text(encoding="utf-8"))["thresholds_by_track"]
    published = _publication_times()
    min_px = int(math.ceil(min_patch_ha * 1e4 / px ** 2))
    pa_km2 = px * px / 1e6
    passes = [p for p in list_passes(aoi) if p["track"] in FULL_TRACKS]
    entries = []
    for track in sorted({p["track"] for p in passes}):
        tp = [p for p in passes if p["track"] == track]
        T = float(thr[track]["threshold_db"])
        base = tp[0]
        b = load_pass(base, prof)
        base_cls = {name: wt.classify(b["hh"], b["hv"], T + d, px) for name, d in LEVELS}
        e = _entry_common(base, published)
        e.update(is_baseline=True, threshold_db=T, threshold_method=thr[track].get("method"))
        entries.append(e)
        print(f"[j1] {track}: baseline {base['date']}, T = {T} dB, {len(tp) - 1} later passes")
        for p in tp[1:]:
            a = load_pass(p, prof)
            areas, files, mid_mask = {}, {}, None
            for name, d in LEVELS:
                ac = wt.classify(a["hh"], a["hv"], T + d, px)
                bc = base_cls[name]
                n2o = ac["open_water"] & ~bc["open_water"] & ac["valid"] & bc["valid"]
                n2o = wt.remove_small(n2o, min_px)
                areas[name] = round(float(n2o.sum()) * pa_km2, 2)
                if n2o.any():
                    dist = np.minimum(np.rint(ndimage.distance_transform_edt(~n2o) * px), NODATA - 1).astype("uint16")
                else:
                    dist = np.full(n2o.shape, NODATA, "uint16")
                files[name] = f"dist_{track}_{p['date']}_{name}.tif"
                write_tif(rd / files[name], dist, prof, "uint16", NODATA)
                if name == "mid":
                    mid_mask = n2o
            lo, hi, mid = min(areas.values()), max(areas.values()), areas["mid"]
            bounds = write_png_4326(rd / f"new_water_{track}_{p['date']}.png", mask_rgba(mid_mask, "00bcd4"), prof)
            e = _entry_common(p, published)
            e.update(is_baseline=False, threshold_db=T, threshold_method=thr[track].get("method"),
                     tested_at_db=[round(T - 1, 2), T, round(T + 1, 2)],
                     baseline={"date": base["date"], "granule_id": base["receipt"].get("granule_id"),
                               "acquired_utc": _acquired(base)},
                     new_water_km2=areas, range_within_25pct=bool(mid > 0 and (hi - lo) / 2.0 <= 0.25 * mid),
                     files=files, overlay={"url": f"radar_rule/new_water_{track}_{p['date']}.png", "bounds": bounds})
            entries.append(e)
            print(f"[j1] {track} {p['date']}: new water {areas} km2, published {e['published_utc']}")
    entries.sort(key=lambda x: x["acquired_utc"])
    index = {"aoi": aoi, "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
             "min_patch_ha": min_patch_ha, "grid": {"crs": prof["crs"], "pixel_m": px},
             "levels": {"strict": "T - 1 dB", "mid": "T", "loose": "T + 1 dB"}, "passes": entries}
    (rd / "index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
    print(f"[j1] wrote {len(entries)} passes -> {rd / 'index.json'}")
    return index


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--aoi", default="kazipur")
    ap.add_argument("--min-patch-ha", type=float, default=1.0)
    a = ap.parse_args()
    run(a.aoi, a.min_patch_ha)
