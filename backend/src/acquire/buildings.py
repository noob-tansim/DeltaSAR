"""Building footprints for the AOI from Google Open Buildings v3, streamed (the 8.4 GB tile never lands on disk).

  python -m src.acquire.buildings --aoi kazipur

HTTP stream -> gzip decompress -> keep rows inside the AOI bbox with confidence >= MIN_CONF -> write
  cache/vector/buildings_<aoi>.csv      lon, lat, area_m2, confidence (centroids, used for counts)
  cache/vector/buildings_<aoi>.geojson  polygons (used for the map, clipped near sites by exposure.py)
  cache/vector/buildings_<aoi>_receipt.json
Resumes after a dropped connection with an HTTP Range request, feeding the same decompressor.
Files are written as .part and renamed only when the whole tile has been read.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import sys
import time
import zlib

import requests

from src.config import AOIS, VECTOR

TILE = "39f"   # S2 level-4 cell covering the Kazipur AOI (from the Open Buildings tiles.geojson)
URL = f"https://storage.googleapis.com/open-buildings-data/v3/polygons_s2_level_4_gzip/{TILE}_buildings.csv.gz"
MIN_CONF = 0.7
CHUNK = 1 << 20


def stream(url, log):
    """Yield decompressed text chunks; resume with Range on errors (up to 20 retries)."""
    dec = zlib.decompressobj(zlib.MAX_WBITS | 32)
    offset, retries, total, t0, last = 0, 0, None, time.time(), 0
    while True:
        try:
            hdr = {"Range": f"bytes={offset}-"} if offset else {}
            with requests.get(url, headers=hdr, stream=True, timeout=120) as r:
                r.raise_for_status()
                if offset and r.status_code != 206:
                    raise RuntimeError("server ignored Range; cannot resume")
                if total is None:
                    total = int(r.headers.get("Content-Length", 0))
                for chunk in r.iter_content(CHUNK):
                    offset += len(chunk)
                    out = dec.decompress(chunk)
                    if out:
                        yield out
                    if offset - last >= 100 * CHUNK:
                        last = offset; el = time.time() - t0; sp = offset / el / 1e6
                        eta = (total - offset) / (offset / el) / 60 if total else float("nan")
                        log(f"{offset / 1e9:.2f}/{total / 1e9:.2f} GB, {sp:.1f} MB/s, ETA {eta:.0f} min")
            tail = dec.flush()
            if tail:
                yield tail
            log(f"done: {offset / 1e9:.2f} GB in {(time.time() - t0) / 60:.1f} min")
            return
        except (requests.RequestException, RuntimeError, OSError) as exc:
            retries += 1
            log(f"stream error at {offset / 1e9:.2f} GB ({exc!r}); retry {retries}/20")
            if retries > 20:
                raise
            time.sleep(min(60, 2 ** retries))


def run(aoi: str):
    w, s, e, n = AOIS[aoi]["bbox"]
    VECTOR.mkdir(parents=True, exist_ok=True)
    logf = open(VECTOR / f"buildings_{aoi}_download.log", "a", encoding="utf-8")

    def log(msg):
        line = f"{dt.datetime.now().isoformat(timespec='seconds')} {msg}"
        print(line, flush=True); logf.write(line + "\n"); logf.flush()

    csv_part, gj_part = VECTOR / f"buildings_{aoi}.csv.part", VECTOR / f"buildings_{aoi}.geojson.part"
    kept = rows = 0
    with open(csv_part, "w", newline="", encoding="utf-8") as fc, open(gj_part, "w", encoding="utf-8") as fg:
        wc = csv.writer(fc); wc.writerow(["lon", "lat", "area_m2", "confidence"])
        fg.write('{"type":"FeatureCollection","features":[\n')
        buf, header, first = "", None, True
        csv.field_size_limit(sys.maxsize if sys.maxsize < 2 ** 31 else 2 ** 31 - 1)
        for text in stream(URL, log):
            buf += text.decode("utf-8")
            lines = buf.split("\n"); buf = lines.pop()
            for row in csv.reader(lines):
                if not row:
                    continue
                if header is None:
                    header = {k: i for i, k in enumerate(row)}; continue
                rows += 1
                lat, lon = float(row[header["latitude"]]), float(row[header["longitude"]])
                if not (s <= lat <= n and w <= lon <= e):
                    continue
                conf = float(row[header["confidence"]])
                if conf < MIN_CONF:
                    continue
                area = float(row[header["area_in_meters"]])
                wc.writerow([f"{lon:.6f}", f"{lat:.6f}", f"{area:.1f}", f"{conf:.3f}"])
                ring = _wkt_ring(row[header["geometry"]])
                if ring:
                    fg.write(("" if first else ",\n") + json.dumps(
                        {"type": "Feature", "properties": {"lon": round(lon, 6), "lat": round(lat, 6), "area_m2": round(area, 1),
                                                           "confidence": round(conf, 3)},
                         "geometry": {"type": "Polygon", "coordinates": [ring]}}, separators=(",", ":")))
                    first = False
                kept += 1
        fg.write("\n]}\n")
    csv_part.replace(VECTOR / f"buildings_{aoi}.csv")
    gj_part.replace(VECTOR / f"buildings_{aoi}.geojson")
    rc = {"source": "Google Open Buildings v3 polygons (S2 level-4 tile %s)" % TILE, "url": URL,
          "licence": "CC BY 4.0 or ODbL v1.0 (user's choice), (c) Google", "min_confidence": MIN_CONF,
          "bbox": [w, s, e, n], "rows_read": rows, "buildings_kept": kept,
          "imagery_note": "footprints detected by a model on satellite imagery up to ~2023; not a damage survey",
          "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")}
    (VECTOR / f"buildings_{aoi}_receipt.json").write_text(json.dumps(rc, indent=1))
    log(f"kept {kept} buildings (conf >= {MIN_CONF}) of {rows} rows -> {VECTOR / f'buildings_{aoi}.csv'}")


def _wkt_ring(wkt: str):
    """POLYGON((x y, x y, ...)) or MULTIPOLYGON -> first outer ring as [[x, y], ...]."""
    i = wkt.find("((")
    if i < 0:
        return None
    body = wkt[i:].lstrip("(").split(")")[0]
    try:
        return [[round(float(a), 6), round(float(b), 6)] for a, b in (p.split() for p in body.split(","))]
    except ValueError:
        return None


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--aoi", default="kazipur")
    run(ap.parse_args().aoi)
