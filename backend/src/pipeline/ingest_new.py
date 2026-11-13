"""Auto-ingest slot: pick up new NISAR GCOV passes, cut them, refresh what depends on them. Idempotent.

  python -m src.pipeline.ingest_new                # local folders + ASF/CMR, then refresh if anything new
  python -m src.pipeline.ingest_new --no-remote    # local folders only
  python -m src.pipeline.ingest_new --dry-run      # only report what it would do

Steps
 1. Local: Data/Track69 and Data/Track19 (and their subfolders) for GCOV .h5 whose date+track is not cut yet.
    Each file is checked before cutting: opens with h5py, HHHH exists, a 512x512 block from the last quarter is
    not all zero (an interrupted copy is zero-filled), size matches the inventory when the granule is listed.
 2. Remote: CMR search (earthaccess, saved Earthdata login) for GCOV granules over the AOI on FULL_TRACKS newer
    than the newest cut date of that track. New rows are appended to the inventory CSV, then stream-cut
    (AOI window only). One granule per track+date: full frame (_F_) and DHDH preferred.
 3. Refresh: run_aoi (water per date, banklines, pairs, recalibration) and the water-extent forecast,
    which scores the forecast that was made before each new pass.
 4. Append an entry to outputs/<aoi>/ingest_log.json.
GUNW files (interferograms) are listed in the log but not cut (not used by the change rules).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import pathlib
import re
import time

import h5py
import numpy as np

from src.acquire import nisar_subset as ns
from src.config import AOIS, FULL_TRACKS, ROOT, aoi_dir, out_dir

DATA = ROOT / "Data"
INVENTORY = ROOT / "NISAR_Jamuna_granule_inventory.csv"
COLLECTION = "NISAR_L2_GCOV_PROVISIONAL_V1"
GUNW_RE = re.compile(r"NISAR_L2_\w\w_GUNW_\d{3}_(\d{3})_([AD])_.*?_(\d{8})T\d{6}_\d{8}T\d{6}_(\d{8})T")


def cut_keys(aoi):
    keys = set()
    for f in aoi_dir(aoi, "sar").glob("nisar_*_HHHH_db.tif"):
        m = re.search(r"nisar_(\d{8})_(\d{3}[AD])_HHHH", f.name)
        if m:
            keys.add((m.group(2), m.group(1)))
    return keys


def read_inventory():
    with open(INVENTORY, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows


def verify_local(path: pathlib.Path, inv_by_granule) -> tuple[bool, str]:
    try:
        with h5py.File(path, "r") as f:
            d = f[ns.GRID]["HHHH"]
            r0, c0 = int(d.shape[0] * 0.8), int(d.shape[1] * 0.5)
            blk = d[r0:r0 + 512, c0:c0 + 512]
            if not np.any(blk):
                return False, "last-quarter block is all zero (incomplete copy?)"
    except Exception as exc:
        return False, f"cannot read: {exc!r}"
    row = inv_by_granule.get(path.stem)
    if row and row.get("size_MB"):
        mb = path.stat().st_size / 1e6
        if mb < 0.97 * float(row["size_MB"]):
            return False, f"size {mb:.0f} MB < inventory {row['size_MB']} MB"
    return True, "ok"


def scan_local(aoi, done, inv_by_granule, dry):
    found, gunw = [], []
    for sub in ("Track69", "Track19"):
        for p in sorted((DATA / sub).rglob("*.h5")) if (DATA / sub).exists() else []:
            g = GUNW_RE.search(p.name)
            if g:
                gunw.append({"file": p.name, "track": g.group(1) + g.group(2), "dates": [g.group(3), g.group(4)]})
                continue
            try:
                meta = ns.parse_name(p.name)
            except SystemExit:
                continue
            key = (meta["track_id"], meta["date"])
            if key in done or meta["track_id"] not in FULL_TRACKS:
                continue
            ok, why = verify_local(p, inv_by_granule)
            entry = {"source": "local", "file": str(p), "track": key[0], "date": key[1], "check": why}
            if ok and not dry:
                row = inv_by_granule.get(p.stem)
                ns.cut(str(p), p.name, aoi, cmr_id=row["cmr_id"] if row else None)
                entry["cut"] = True; entry["cmr_id"] = row["cmr_id"] if row else None
                if not row:
                    entry["note"] = "not in the inventory CSV: cut without a cmr id"
                done.add(key)
            found.append(entry)
    return found, gunw


def search_remote(aoi, done, rows):
    import earthaccess
    earthaccess.login(strategy="netrc")
    newest = {}
    for tr, d in done:
        newest[tr] = max(newest.get(tr, "00000000"), d)
    start = min(newest.values()) if newest else "20260601"
    start_iso = f"{start[:4]}-{start[4:6]}-{start[6:]}"
    w, s, e, n = AOIS[aoi]["bbox"]
    res = earthaccess.search_data(short_name=COLLECTION, bounding_box=(w, s, e, n),
                                  temporal=(start_iso, dt.date.today().isoformat()), count=200)
    cands = {}
    for g in res:
        links = [u for u in g.data_links() if u.endswith(".h5")]
        if not links:
            continue
        name = links[0].rsplit("/", 1)[1][:-3]
        try:
            meta = ns.parse_name(name)
        except SystemExit:
            continue
        key = (meta["track_id"], meta["date"])
        if meta["track_id"] not in FULL_TRACKS or key in done or meta["date"] <= newest.get(meta["track_id"], "0"):
            continue
        score = (("_F_" in name), meta["pol"] == "DHDH", -float(g.size() or 0))
        prev = cands.get(key)
        if prev is None or score > prev[0]:
            cands[key] = (score, name, links[0], g["meta"]["concept-id"], float(g.size() or 0), meta)
    known = {r["granule"] for r in rows}
    new_rows = []
    for key, (_, name, url, cmr, size, meta) in sorted(cands.items(), key=lambda kv: kv[0][1]):
        if name not in known:
            new_rows.append({"collection": COLLECTION, "date": f"{meta['date'][:4]}-{meta['date'][4:6]}-{meta['date'][6:]}",
                             "granule": name, "cycle": meta["cycle"], "track": meta["track"],
                             "direction": "Ascending" if meta["dir"] == "A" else "Descending", "frame": meta["frame"],
                             "mode": meta["mode"], "polarization": meta["pol"], "size_MB": round(size, 1),
                             "h5_url": url, "browse_png": "", "cmr_id": cmr})
    return cands, new_rows


def append_inventory(new_rows):
    if not new_rows:
        return
    with open(INVENTORY, encoding="utf-8") as f:
        header = next(csv.reader(f))
    with open(INVENTORY, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header)
        for r in new_rows:
            w.writerow({k: r.get(k, "") for k in header})


def stream_cut(aoi, cands, done, retries=3):
    import earthaccess
    out = []
    for key, (_, name, url, cmr, size, meta) in sorted(cands.items(), key=lambda kv: kv[0][1]):
        if key in done:
            continue
        t0 = time.time(); err = None
        for _ in range(retries):
            try:
                fobj = earthaccess.open([url])[0]
                ns.cut(fobj, name, aoi, cmr_id=cmr, url=url)
                err = None; break
            except Exception as exc:     # network hiccups: retry
                err = repr(exc)
        out.append({"source": "asf", "granule": name, "track": key[0], "date": key[1], "cmr_id": cmr,
                    "seconds": round(time.time() - t0), "cut": err is None, "error": err})
        if err is None:
            done.add(key)
    return out


def refresh(aoi):
    """run_aoi + forecast (which scores the previous forecast against the new pass, refits, writes timeline.json),
    built in a staging folder and swapped in atomically so the live dashboard never sees half-written files."""
    from src.pipeline.publish import build_and_swap
    r = build_and_swap(("run_aoi", "forecast", "insights"))
    if not r["ok"]:
        raise RuntimeError(f"refresh failed at {r['failed_step']}; live outputs unchanged")


def run(aoi="kazipur", remote=True, dry=False, force_refresh=False) -> dict:
    t0 = time.time()
    rows = read_inventory()
    inv_by_granule = {r["granule"]: r for r in rows}
    done = cut_keys(aoi)
    before = set(done)
    entry = {"started_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "dry_run": dry}
    entry["local"], entry["gunw_seen"] = scan_local(aoi, done, inv_by_granule, dry)
    entry["remote"] = []
    if remote:
        try:
            cands, new_rows = search_remote(aoi, done, rows)
            entry["remote_found"] = [{"track": k[0], "date": k[1], "granule": v[1], "cmr_id": v[3]} for k, v in sorted(cands.items())]
            if not dry:
                append_inventory(new_rows)
                entry["inventory_rows_added"] = len(new_rows)
                entry["remote"] = stream_cut(aoi, cands, done)
        except Exception as exc:
            entry["remote_error"] = repr(exc)
    new = sorted(done - before)
    entry["new_passes"] = [f"{d} {t}" for t, d in sorted(new, key=lambda k: k[1])]
    if (new or force_refresh) and not dry:
        refresh(aoi)
        entry["refreshed"] = True
    entry["seconds"] = round(time.time() - t0)
    log = out_dir(aoi) / "ingest_log.json"
    hist = json.loads(log.read_text()) if log.exists() else []
    hist.append(entry)
    log.write_text(json.dumps(hist, indent=1))
    print(json.dumps({k: entry[k] for k in ("new_passes", "seconds") if k in entry}))
    return entry


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--aoi", default="kazipur")
    ap.add_argument("--no-remote", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--refresh", action="store_true", help="refresh even if nothing new")
    a = ap.parse_args()
    run(a.aoi, remote=not a.no_remote, dry=a.dry_run, force_refresh=a.refresh)
