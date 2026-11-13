"""Custom date comparison: bank loss between any two observed passes of ONE track (same rules as the preset pairs).

  python -m src.compute.compare --track 069A --before 20260618 --after 20260910 [--confirm 20260922]

Mixing tracks is refused: look direction, incidence angle and (for 019D) the 20 m mode differ, so backscatter is not
comparable pixel by pixel. If no confirm date is given, the next available pass of the same track is used; if there
is none the result is UNCONFIRMED. Results are cached as outputs/<aoi>/pairs/custom_<track>_<before>_<after>[_<confirm>].*
"""
from __future__ import annotations

import argparse
import json
import time

from rasterio.warp import Resampling

from src.compute import exposure
from src.compute import water as wt
from src.config import AOIS, aoi_dir, base_profile, out_dir


def pair_id(track, before, after, confirm):
    return f"custom_{track}_{before}_{after}" + (f"_{confirm}" if confirm else "")


def compare(aoi, track, before, after, confirm=None, auto_confirm=True) -> dict:
    from src.pipeline.run_aoi import list_passes, load_pass, to_grid
    t0 = time.time()
    if before >= after:
        raise ValueError("before must be earlier than after")
    passes = {p["date"]: p for p in list_passes(aoi) if p["track"] == track}
    for d in (before, after) + ((confirm,) if confirm else ()):
        if d not in passes:
            raise ValueError(f"{d} is not an observed pass of track {track}")
    if confirm is None and auto_confirm:
        later = sorted(d for d in passes if d > after)
        confirm = later[0] if later else None
    pid = pair_id(track, before, after, confirm)
    od = out_dir(aoi); path = od / "pairs" / f"{pid}.json"
    if path.exists():
        info = json.loads(path.read_text()); info["cached"] = True
        return _stage(aoi, info)
    prof = base_profile(aoi); px = AOIS[aoi]["grid_m"]
    river = to_grid(aoi_dir(aoi, "dem") / "river_mask.tif", prof, Resampling.nearest) >= 0.5
    summ = json.loads((od / "summary.json").read_text())
    tthr = summ["thresholds_by_track"][track]
    b, a = load_pass(passes[before], prof), load_pass(passes[after], prof)
    c = load_pass(passes[confirm], prof) if confirm else None
    ch = wt.change(b, a, px, tthr["threshold_db"], river, c, erosion=True)
    m = ch.pop("masks"); ch.pop("masks_by_threshold")
    pr = {"id": pid, "track": track, "before": before, "after": after,
          "story": f"Custom comparison {before} to {after} on track {track}" + (f", confirmed by {confirm}" if confirm else " (UNCONFIRMED)")}
    info = {"pair": pr, **ch, "confirm_pass": confirm, "custom": True,
            "receipts": {"before": passes[before]["receipt"], "after": passes[after]["receipt"]},
            "threshold": tthr, "caveat": wt.CAVEAT}
    info["exposure"] = exposure.pair_exposure(aoi, prof, pr, info, m, od, b, a)
    info["compute_seconds"] = round(time.time() - t0, 1)
    path.write_text(json.dumps(info, indent=1))
    return _stage(aoi, info)


STAGE_WARN_RATIO = 1.3


def _stage(aoi, info):
    """Attach GloFAS discharge on both dates; warn when river level differs a lot (change then mostly = water level)."""
    fc = out_dir(aoi) / "forecast" / "forecast.json"
    if not fc.exists():
        return info
    q = {p["date"]: p["q"] for p in json.loads(fc.read_text())["model"]["points"]}
    qb, qa = q.get(info["pair"]["before"]), q.get(info["pair"]["after"])
    info["discharge_m3s"] = {"before": round(qb) if qb else None, "after": round(qa) if qa else None,
                             "source": "GloFAS via Open-Meteo, Jamuna main stem near Sirajganj"}
    if qb and qa:
        r = max(qb, qa) / min(qb, qa)
        info["stage_warning"] = (f"River flow differs {r:.1f}x between the dates ({round(qb):,} vs {round(qa):,} m3/s): "
                                 "much of the land-to-water change is likely water level, not bank erosion. Prefer dates with similar flow."
                                 if r >= STAGE_WARN_RATIO else None)
    return info


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--aoi", default="kazipur"); ap.add_argument("--track", required=True)
    ap.add_argument("--before", required=True); ap.add_argument("--after", required=True); ap.add_argument("--confirm")
    a = ap.parse_args()
    r = compare(a.aoi, a.track, a.before, a.after, a.confirm)
    print(json.dumps({k: r[k] for k in ("mainland_bank_loss_ha_range", "bank_loss_confirmed", "compute_seconds") if k in r}))
