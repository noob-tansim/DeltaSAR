"""J2: fill the rain and river inputs of the alert layer. Real data only; every row keeps its source.

  python -m jobs.j2_load_inputs rain            # NASA IMERG V07 Early daily through NASA SERVIR ClimateSERV (no login)
  python -m jobs.j2_load_inputs river           # FFWC public pages: station charts (3-hourly observed) + forecast table
  python -m jobs.j2_load_inputs all
  python -m jobs.j2_load_inputs all --offline   # load the CSV snapshots in data/ without any network call

Snapshots (kept in git, so a server without internet still has them):
  data/rain_daily.csv      date,mm,source,fetched_utc
  data/river_levels.csv    station,valid_local,level_m,kind,lead_days,issued_local,source_url,entered_by

Assumptions, stated because they decide what a REPLAY sees:
  rain   a day's total counts as known 36 h after the end of that UTC day (IMERG Early daily ran about two days behind
         when checked on 12 Nov 2026), or at the moment it was fetched if that is earlier.
  river  an observed value counts as known at its own time; the forecast in the table counts as known at 06:00 local
         on the table's date. FFWC writes chart times as local wall time.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import time
from pathlib import Path

import requests

from src.alerts import settings
from src.alerts.db import RainDaily, RiverReading, init_engine, session_scope
from src.alerts.types import DHAKA, RAIN_DATA_MAX_MM, RIVER_MAX_M, RIVER_MIN_M

RAIN_CSV = settings.DATA / "rain_daily.csv"
RIVER_CSV = settings.DATA / "river_levels.csv"
CSERV = "https://climateserv.servirglobal.net/api"
IMERG_EARLY_DAILY = 227
RAIN_SOURCE = ("NASA IMERG V07 Early daily (GPM), wettest cell in the covered area, "
               "through NASA SERVIR ClimateSERV (dataset 227, max over the area)")
FFWC_TABLE = "http://old.ffwc.gov.bd/ffwc_charts/waterlevelfcast.php"
FFWC_STATION = "http://old.ffwc.gov.bd/ffwc_charts/index.php?stid={stid}"
UTC = dt.timezone.utc


# ---------------------------------------------------------------- rain
def fetch_rain(start: dt.date, end: dt.date) -> list[tuple[str, float]]:
    w, s, e, n = settings.AOI_BBOX
    geom = {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}
    r = requests.get(f"{CSERV}/submitDataRequest/", timeout=60, params={
        "datatype": IMERG_EARLY_DAILY, "begintime": start.strftime("%m/%d/%Y"), "endtime": end.strftime("%m/%d/%Y"),
        "intervaltype": 0, "operationtype": 0, "geometry": json.dumps(geom)})
    r.raise_for_status()
    job = r.json()[0]
    for _ in range(60):
        p = requests.get(f"{CSERV}/getDataRequestProgress/", params={"id": job}, timeout=30).json()
        if p and float(p[0]) >= 100:
            break
        if p and float(p[0]) < 0:
            raise RuntimeError("ClimateSERV reported an error for this request")
        time.sleep(3)
    else:
        raise TimeoutError("ClimateSERV did not finish in time")
    data = requests.get(f"{CSERV}/getDataFromRequest/", params={"id": job}, timeout=60).json()["data"]
    out = []
    for row in data:
        val = row.get("value") or {}
        if not val:
            continue
        mm = float(next(iter(val.values())))
        if mm < 0 or mm > RAIN_DATA_MAX_MM:       # fill values: keep the day out rather than guess
            continue
        m, d, y = row["date"].split("/")
        out.append((f"{y}-{m}-{d}", round(mm, 2)))
    return sorted(out)


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def load_rain(offline: bool) -> int:
    rows = {r["date"]: r for r in _read_csv(RAIN_CSV)}
    if not offline:
        now = dt.datetime.now(UTC)
        fetched = fetch_rain(dt.date(2026, 6, 1), now.date())
        for date, mm in fetched:
            if date not in rows:
                rows[date] = {"date": date, "mm": f"{mm}", "source": RAIN_SOURCE,
                              "fetched_utc": now.isoformat(timespec="seconds")}
        with open(RAIN_CSV, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["date", "mm", "source", "fetched_utc"])
            w.writeheader()
            for date in sorted(rows):
                w.writerow(rows[date])
    n = 0
    with session_scope() as s:
        for date, r in sorted(rows.items()):
            day_end = dt.datetime.fromisoformat(date).replace(tzinfo=UTC) + dt.timedelta(days=1)
            fetched_at = dt.datetime.fromisoformat(r["fetched_utc"])
            visible = min(day_end + dt.timedelta(hours=36), fetched_at)
            row = s.get(RainDaily, date)
            if row is None:
                s.add(RainDaily(date=date, mm=float(r["mm"]), source=r["source"], visible_utc=visible))
                n += 1
    print(f"[j2] rain: {len(rows)} days in {RAIN_CSV.name}, {n} new in the database"
          + (f"; newest {max(rows)}" if rows else ""))
    return n


# ---------------------------------------------------------------- river
_PT = re.compile(r"Date\.UTC\((\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\)\s*,\s*([\d.]+)")


def parse_station_page(html: str) -> dict[str, list[tuple[dt.datetime, float]]]:
    """{'observed': [(local time, level)], 'forecast': [...]} from a station chart page. JS months start at 0."""
    js = " ".join(re.findall(r"<script[^>]*>(.*?)</script>", html, flags=re.S))
    out: dict[str, list[tuple[dt.datetime, float]]] = {"observed": [], "forecast": []}
    parts = re.split(r"name:\s*'", js)[1:]
    for part in parts:
        name = part.split("'", 1)[0].lower()
        kind = "observed" if name.startswith("observed") else "forecast" if name.startswith("forecast") else None
        if kind is None:
            continue
        for y, mo, d, h, mi, v in _PT.findall(part):
            t = dt.datetime(int(y), int(mo) + 1, int(d), int(h), int(mi), tzinfo=DHAKA)
            out[kind].append((t, float(v)))
    return out


def parse_forecast_table(html: str) -> tuple[list[dt.date], dict[str, list[float | None]], dict[str, float]]:
    """(dates of the three columns, {station: [obs day-1, obs day0, forecast day+1]}, {station: danger level})."""
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.S)
    cells = [[re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", c)).strip()
              for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, flags=re.S)] for r in rows]
    m = re.search(r"WATER LEVELS\s*:\s*(\d{2})-(\d{2})-(\d{4})", re.sub(r"<[^>]+>", " ", html))
    if not m:
        raise ValueError("FFWC table: date line not found")
    table_date = dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    head = next(c for c in cells if "Station" in c)
    dm = [x for x in head if re.fullmatch(r"\d{2}-\d{2}", x)]
    dates = []
    for x in dm:
        d, mo = int(x[:2]), int(x[3:])
        yr = table_date.year + (1 if (mo == 1 and table_date.month == 12) else -1 if (mo == 12 and table_date.month == 1) else 0)
        dates.append(dt.date(yr, mo, d))
    i0 = head.index(dm[0])
    levels: dict[str, list[float | None]] = {}
    dl: dict[str, float] = {}
    for c in cells:
        if len(c) > i0 + len(dm) - 1 and re.fullmatch(r"[\d.]+", c[2] if len(c) > 2 else ""):
            vals: list[float | None] = []
            for x in c[i0:i0 + len(dm)]:
                vals.append(float(x) if re.fullmatch(r"[\d.]+", x) and float(x) > 0 else None)
            levels[c[1]], dl[c[1]] = vals, float(c[2])
    return dates, levels, dl


def fetch_river() -> list[dict[str, str]]:
    st = json.loads((settings.DATA / "stations.json").read_text(encoding="utf-8"))["stations"]
    out: list[dict[str, str]] = []
    table = requests.get(FFWC_TABLE, timeout=40).text
    dates, levels, dl = parse_forecast_table(table)
    issued = dt.datetime.combine(dates[-2], dt.time(6, 0), tzinfo=DHAKA)
    for s in st:
        if not s.get("use_for_rule", True):
            continue
        name, ffwc = s["name"], s.get("ffwc_name", s["name"])
        if ffwc in dl and abs(dl[ffwc] - float(s["danger_level_m"])) > 0.005:
            print(f"[j2] WARNING: FFWC now shows danger level {dl[ffwc]} m for {name}; data/stations.json says "
                  f"{s['danger_level_m']} m. Check and update the file by hand.")
        url = FFWC_STATION.format(stid=s["stid"])
        series = parse_station_page(requests.get(url, timeout=40).text)
        for t, v in series["observed"]:
            out.append({"station": name, "valid_local": t.isoformat(timespec="minutes"), "level_m": f"{v:.2f}",
                        "kind": "observed", "lead_days": "0", "issued_local": t.isoformat(timespec="minutes"),
                        "source_url": url, "entered_by": "jobs.j2 (FFWC station chart)"})
        fc = (levels.get(ffwc) or [None])[-1]
        if fc is not None:
            valid = dt.datetime.combine(dates[-1], dt.time(6, 0), tzinfo=DHAKA)
            out.append({"station": name, "valid_local": valid.isoformat(timespec="minutes"), "level_m": f"{fc:.2f}",
                        "kind": "forecast", "lead_days": str((dates[-1] - dates[-2]).days),
                        "issued_local": issued.isoformat(timespec="minutes"), "source_url": FFWC_TABLE,
                        "entered_by": "jobs.j2 (FFWC forecast table)"})
    return out


def load_river(offline: bool) -> int:
    fields = ["station", "valid_local", "level_m", "kind", "lead_days", "issued_local", "source_url", "entered_by"]
    key = lambda r: (r["station"], r["valid_local"], r["kind"], r["issued_local"])  # noqa: E731
    rows = {key(r): r for r in _read_csv(RIVER_CSV)}
    if not offline:
        for r in fetch_river():
            rows.setdefault(key(r), r)
        with open(RIVER_CSV, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for k in sorted(rows):
                w.writerow(rows[k])
    n = skipped = 0
    with session_scope() as s:
        have = {(r.station, r.valid_utc, r.kind, r.issued_utc) for r in s.query(RiverReading)}
        for r in rows.values():
            level = float(r["level_m"])
            if not (RIVER_MIN_M <= level <= RIVER_MAX_M):
                skipped += 1
                continue
            valid = dt.datetime.fromisoformat(r["valid_local"]).astimezone(UTC)
            issued = dt.datetime.fromisoformat(r["issued_local"]).astimezone(UTC)
            if (r["station"], valid, r["kind"], issued) in have:
                continue
            s.add(RiverReading(station=r["station"], valid_utc=valid, level_m=level, kind=r["kind"],
                               lead_days=int(r["lead_days"]), issued_utc=issued, source_url=r["source_url"],
                               entered_by=r["entered_by"]))
            n += 1
    newest = max((r["valid_local"] for r in rows.values()), default=None)
    print(f"[j2] river: {len(rows)} rows in {RIVER_CSV.name}, {n} new in the database, {skipped} outside the allowed range"
          + (f"; newest {newest}" if newest else ""))
    return n


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["rain", "river", "all"])
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args()
    init_engine()
    for what, fn in (("rain", load_rain), ("river", load_river)):
        if a.what in (what, "all"):
            try:
                fn(a.offline)
            except Exception as exc:            # one source being down must not stop the other
                print(f"[j2] {what}: live fetch failed ({exc!r}); loading the snapshot instead")
                fn(True)
