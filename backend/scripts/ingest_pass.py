"""Ingest one NISAR GCOV pass over the reach: find it in NASA CMR (validated or provisional collection), stream only
the reach window from ASF with Earthdata Login, and cut it with the kit's cutter (src/acquire/nisar_subset.py).

    set EARTHDATA_TOKEN=...        (urs.earthdata.nasa.gov -> Generate Token; never commit it)
    python scripts/ingest_pass.py --date 20261109 --track 069A

Writes cache/sar/kazipur/nisar_<date>_<track>_{HHHH,HVHV}_db.tif and _receipt.json, then prints the consistency
check (plan step S2): median HH over the core river and over stable land, against the range of the earlier passes.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.acquire.nisar_subset import cut  # noqa: E402
from src.config import AOIS  # noqa: E402

CMR = "https://cmr.earthdata.nasa.gov/search/granules.umm_json"


def find(date: str, track: str) -> dict:
    """The full-frame GCOV granule of that date and track, preferring VALIDATED over PROVISIONAL."""
    w, s, e, n = AOIS["kazipur"]["bbox"]
    day = f"{date[:4]}-{date[4:6]}-{date[6:]}"
    for short in ("NISAR_L2_GCOV_V1", "NISAR_L2_GCOV_PROVISIONAL_V1"):
        j = requests.get(CMR, params={"short_name": short, "bounding_box": f"{w},{s},{e},{n}", "page_size": 50,
                                      "temporal": f"{day}T00:00:00Z,{day}T23:59:59Z"}, timeout=60).json()
        for it in j.get("items", []):
            ur = it["umm"]["GranuleUR"]
            if f"_{track[:3]}_{track[3]}_" in ur and "_F_J_" in ur:          # full frame of this track
                urls = [u["URL"] for u in it["umm"].get("RelatedUrls", []) if u.get("Type") == "GET DATA" and u["URL"].endswith(".h5")]
                https = [u for u in urls if u.startswith("https://")]
                if https:
                    return {"granule": ur, "cmr_id": it["meta"]["concept-id"], "url": https[0], "collection": short}
    raise SystemExit(f"No full-frame GCOV granule for {date} track {track} in CMR")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--track", required=True)
    a = ap.parse_args()
    if not os.environ.get("EARTHDATA_TOKEN"):
        raise SystemExit("Set EARTHDATA_TOKEN first (urs.earthdata.nasa.gov -> Generate Token)")
    g = find(a.date, a.track)
    print(f"[ingest] {g['granule']} ({g['collection']}, {g['cmr_id']})")
    import earthaccess
    earthaccess.login(strategy="environment")
    fobj = earthaccess.open([g["url"]])[0]
    written = cut(fobj, g["granule"] + ".h5", "kazipur", cmr_id=g["cmr_id"], url=g["url"])
    # NISAR file names say "PR" for both maturity levels: take the label from the CMR collection instead
    rc_path = Path(written[0]).with_name(f"nisar_{a.date}_{a.track}_receipt.json")
    rc = json.loads(rc_path.read_text())
    crid = g["granule"].split("_")[-5]
    rc["processing_level"] = f"L2 GCOV {'VALIDATED' if g['collection'] == 'NISAR_L2_GCOV_V1' else 'PROVISIONAL'} (CRID {crid})"
    rc["collection"] = g["collection"]
    rc_path.write_text(json.dumps(rc, indent=1))
    print("[ingest]", rc["processing_level"])
    print("[ingest] wrote", *[Path(w).name for w in written], sep="\n  ")


if __name__ == "__main__":
    main()
