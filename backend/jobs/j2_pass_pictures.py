"""J2: water map, radar picture and water areas for passes newer than the kit's run, made exactly as the kit makes them
(src/compute/insights.py and src/pipeline/run_aoi.py), so build_web_data can show them next to the kit's passes.

  python -m jobs.j2_pass_pictures --pass 20261109_069A --river <kit cache/dem/kazipur/river_mask.tif> \
         --daily <kit outputs/kazipur/insights/insights.json> --out <work dir>

For each pass: open water = the kit's water rule at the track threshold (summary.json under DELTASAR_OUTPUTS);
water_km2 and water_outside_channel_km2 as in insights.py; water_<date>_<track>.png (blue) and sar_<date>_<track>.png
(greyscale HH) in EPSG:4326; discharge for the day from the kit's GloFAS daily series. Writes extra_passes.json.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from rasterio.enums import Resampling

from src.compute import water as wt
from src.config import AOIS, base_profile, out_dir
from src.pipeline.run_aoi import grey_rgba, list_passes, load_pass, mask_rgba, to_grid, write_png_4326


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pass", dest="passes", action="append", required=True, help="<date>_<track>, repeatable")
    ap.add_argument("--river", required=True, type=Path)
    ap.add_argument("--daily", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--aoi", default="kazipur")
    a = ap.parse_args()
    prof = base_profile(a.aoi)
    px = AOIS[a.aoi]["grid_m"]
    thr = json.loads((out_dir(a.aoi) / "summary.json").read_text(encoding="utf-8"))["thresholds_by_track"]
    river = to_grid(a.river, prof, Resampling.nearest) >= 0.5
    daily = {d["date"]: d.get("discharge_m3s") for d in json.loads(a.daily.read_text(encoding="utf-8"))["river"]["daily"]}
    by_key = {f"{p['date']}_{p['track']}": p for p in list_passes(a.aoi)}
    a.out.mkdir(parents=True, exist_ok=True)
    rows = []
    for key in a.passes:
        p = by_key[key]
        lp = load_pass(p, prof)
        T = float(thr[p["track"]]["threshold_db"])
        w = wt.classify(lp["hh"], lp["hv"], T, px)["open_water"]
        write_png_4326(a.out / f"water_{p['date']}_{p['track']}.png", mask_rgba(w, "1e78ff"), prof)
        write_png_4326(a.out / f"sar_{p['date']}_{p['track']}.png", grey_rgba(lp["hh"]), prof)
        row = {"date": p["date"], "track": p["track"], "threshold_db": T,
               "water_km2": round(float(w.sum()) * px * px / 1e6, 1),
               "water_outside_channel_km2": round(float((w & ~river).sum()) * px * px / 1e6, 1),
               "discharge_m3s": daily.get(p["date"]),
               "granule_id": p["receipt"].get("granule_id"), "processing_level": p["receipt"].get("processing_level")}
        rows.append(row)
        print("[j2]", row)
    (a.out / "extra_passes.json").write_text(json.dumps({"passes": rows, "made_by": "jobs/j2_pass_pictures.py"}, indent=1),
                                             encoding="utf-8")


if __name__ == "__main__":
    main()
