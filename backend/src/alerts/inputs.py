"""Readers for what the rules look at: radar layers (files written by jobs/j1), river readings and rain (database).

Every reader takes `as_of` and returns only what had been published by then, so LIVE and REPLAY share one code path.
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.alerts import settings
from src.alerts.db import RainDaily, RiverReading
from src.alerts.types import DHAKA, in_aoi
from src.config import NISAR_GAP_UTC

NODATA_DIST = 65535          # uint16 value meaning "no new water anywhere in this layer"
CADENCE_DAYS = 12


def _parse_utc(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(dt.timezone.utc)


def in_radar_gap(as_of: dt.datetime) -> bool:
    g0, g1 = (_parse_utc(x) for x in NISAR_GAP_UTC)
    return g0 <= as_of <= g1


# ---------------------------------------------------------------- radar
@dataclass(frozen=True)
class PassInfo:
    track: str
    date: str                       # YYYYMMDD (UTC acquisition date)
    acquired_utc: dt.datetime
    published_utc: dt.datetime
    publication_source: str
    granule_id: str | None
    cmr_id: str | None
    processing_level: str
    unknown_pct: float
    is_baseline: bool
    baseline: dict[str, Any] = field(default_factory=dict)
    threshold_db: float | None = None
    threshold_method: str | None = None
    tested_at_db: tuple[float, ...] = ()
    new_water_km2: dict[str, float] = field(default_factory=dict)
    range_within_25pct: bool | None = None
    files: dict[str, str] = field(default_factory=dict)
    overlay: dict[str, Any] | None = None

    @property
    def key(self) -> str:
        return f"{self.track}_{self.date}"


def _index_path() -> Path:
    return settings.RADAR_RULE_DIR / "index.json"


@lru_cache(maxsize=4)
def _load_index(path: str, mtime: float) -> tuple[dict[str, Any], tuple[PassInfo, ...]]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    passes = []
    for p in raw["passes"]:
        passes.append(PassInfo(
            track=p["track"], date=p["date"], acquired_utc=_parse_utc(p["acquired_utc"]),
            published_utc=_parse_utc(p["published_utc"]), publication_source=p.get("publication_source", ""),
            granule_id=p.get("granule_id"), cmr_id=p.get("cmr_id"), processing_level=p.get("processing_level", ""),
            unknown_pct=float(p.get("unknown_pct", 0.0)), is_baseline=bool(p.get("is_baseline")),
            baseline=p.get("baseline") or {}, threshold_db=p.get("threshold_db"),
            threshold_method=p.get("threshold_method"), tested_at_db=tuple(p.get("tested_at_db") or ()),
            new_water_km2=p.get("new_water_km2") or {}, range_within_25pct=p.get("range_within_25pct"),
            files=p.get("files") or {}, overlay=p.get("overlay")))
    passes.sort(key=lambda x: x.acquired_utc)
    return raw, tuple(passes)


def radar_passes() -> tuple[PassInfo, ...]:
    """All passes in the radar-rule index, oldest first. Empty if jobs/j1 has not run."""
    p = _index_path()
    if not p.exists():
        return ()
    return _load_index(str(p), p.stat().st_mtime)[1]


def radar_index_meta() -> dict[str, Any]:
    p = _index_path()
    if not p.exists():
        return {}
    raw = _load_index(str(p), p.stat().st_mtime)[0]
    return {k: v for k, v in raw.items() if k != "passes"}


def published_passes(as_of: dt.datetime) -> list[PassInfo]:
    return [p for p in radar_passes() if p.published_utc <= as_of]


def latest_pass(as_of: dt.datetime) -> PassInfo | None:
    """Newest pass (by acquisition) that had been published at as_of."""
    ps = published_passes(as_of)
    return ps[-1] if ps else None


def previous_pass(p: PassInfo) -> PassInfo | None:
    same = [q for q in radar_passes() if q.track == p.track and q.acquired_utc < p.acquired_utc]
    return same[-1] if same else None


def next_expected_local_date(as_of: dt.datetime) -> str | None:
    """Next acquisition on either full-coverage track, from the 12-day repeat cycle (a schedule, not a promise)."""
    best: dt.datetime | None = None
    for track in {p.track for p in radar_passes()}:
        first = [p for p in radar_passes() if p.track == track][0].acquired_utc
        nxt = first
        while nxt <= as_of or in_radar_gap(nxt):       # the instrument was off during the gap
            nxt += dt.timedelta(days=CADENCE_DAYS)
        if best is None or nxt < best:
            best = nxt
    return None if best is None else best.astimezone(DHAKA).date().isoformat()


def sample_raster(path: Path, lat: float, lon: float) -> float | None:
    """Value of the raster cell under a lon/lat point; None outside the raster or on nodata."""
    import rasterio
    from rasterio.warp import transform as warp_xy

    if not path.exists():
        return None
    with rasterio.open(path) as src:
        xs, ys = warp_xy("EPSG:4326", src.crs, [lon], [lat])
        row, col = src.index(xs[0], ys[0])
        if not (0 <= row < src.height and 0 <= col < src.width):
            return None
        v = float(src.read(1, window=((row, row + 1), (col, col + 1)))[0, 0])
        if src.nodata is not None and v == src.nodata:
            return None
        return v


@dataclass(frozen=True)
class RadarInput:
    pass_: PassInfo | None
    in_aoi: bool
    in_river: bool
    d_strict: float | None = None      # metres to the nearest new water at T - 1 dB (fewest water pixels)
    d_mid: float | None = None         # at T
    d_loose: float | None = None       # at T + 1 dB (most water pixels)
    prev_d_mid: float | None = None    # same, at the previous pass of the track
    prev_pass_date: str | None = None


def _dist(p: PassInfo, which: str, lat: float, lon: float) -> float | None:
    name = p.files.get(which)
    if not name:
        return None
    v = sample_raster(settings.RADAR_RULE_DIR / name, lat, lon)
    return None if v is None or v >= NODATA_DIST else v


def radar_for(lat: float, lon: float, as_of: dt.datetime) -> RadarInput:
    p = latest_pass(as_of)
    covered = in_aoi(lat, lon)
    if p is None or not covered:
        return RadarInput(p, covered, False)
    river = sample_raster(settings.AOI_OUT / "layers" / "river_mask.tif", lat, lon) == 1.0
    if p.is_baseline:
        return RadarInput(p, covered, river)
    prev = previous_pass(p)
    prev_d = _dist(prev, "mid", lat, lon) if prev and not prev.is_baseline else None
    return RadarInput(p, covered, river, _dist(p, "strict", lat, lon), _dist(p, "mid", lat, lon),
                      _dist(p, "loose", lat, lon), prev_d, prev.date if prev else None)


# ---------------------------------------------------------------- river
@dataclass(frozen=True)
class Station:
    name: str
    danger_level_m: float
    lat: float | None
    lon: float | None
    stid: int | None
    source_url: str | None


@lru_cache(maxsize=2)
def _stations(path: str, mtime: float) -> tuple[Station, ...]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return tuple(Station(s["name"], float(s["danger_level_m"]), s.get("lat"), s.get("lon"), s.get("stid"),
                         s.get("source_url")) for s in raw["stations"] if s.get("use_for_rule", True))


def stations() -> tuple[Station, ...]:
    p = settings.DATA / "stations.json"
    return _stations(str(p), p.stat().st_mtime) if p.exists() else ()


def station_for(lat: float, lon: float) -> Station | None:
    """Nearest rule station that has a position; the first one if none has."""
    sts = stations()
    if not sts:
        return None
    with_pos = [s for s in sts if s.lat is not None and s.lon is not None]
    if not with_pos:
        return sts[0]
    return min(with_pos, key=lambda s: (s.lat - lat) ** 2 + (s.lon - lon) ** 2)  # type: ignore[operator]


@dataclass(frozen=True)
class Reading:
    level_m: float
    kind: str
    lead_days: int
    valid_utc: dt.datetime
    issued_utc: dt.datetime
    source_url: str
    entered_by: str


@dataclass(frozen=True)
class RiverInput:
    station: Station | None
    reading: Reading | None


def river_for(s: Session, station: Station | None, as_of: dt.datetime) -> RiverInput:
    """Newest reading issued at or before as_of. Among readings of one issue, the latest valid time that is
    not beyond the allowed forecast lead."""
    if station is None:
        return RiverInput(None, None)
    row = s.scalars(select(RiverReading)
                    .where(RiverReading.station == station.name, RiverReading.issued_utc <= as_of,
                           RiverReading.lead_days <= settings.RIVER_MAX_LEAD_DAYS)
                    .order_by(RiverReading.issued_utc.desc(), RiverReading.valid_utc.desc()).limit(1)).first()
    if row is None:
        return RiverInput(station, None)
    return RiverInput(station, Reading(row.level_m, row.kind, row.lead_days, row.valid_utc, row.issued_utc,
                                       row.source_url, row.entered_by))


# ---------------------------------------------------------------- rain
@dataclass(frozen=True)
class RainInput:
    date: str            # YYYY-MM-DD, the UTC day the 24-hour total covers
    mm: float
    source: str
    visible_utc: dt.datetime


def rain_for(s: Session, as_of: dt.datetime) -> RainInput | None:
    """Newest 24-hour total that could be known at as_of."""
    row = s.scalars(select(RainDaily).where(RainDaily.visible_utc <= as_of)
                    .order_by(RainDaily.date.desc()).limit(1)).first()
    return None if row is None else RainInput(row.date, row.mm, row.source, row.visible_utc)


def rain_days(s: Session, as_of: dt.datetime, n: int = 7) -> list[RainInput]:
    rows = s.scalars(select(RainDaily).where(RainDaily.visible_utc <= as_of)
                     .order_by(RainDaily.date.desc()).limit(n)).all()
    return [RainInput(r.date, r.mm, r.source, r.visible_utc) for r in reversed(rows)]


# ---------------------------------------------------------------- unions
@lru_cache(maxsize=2)
def _unions(path: str, mtime: float, names_path: str, names_mtime: float) -> tuple[dict[str, Any], ...]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    names: dict[str, str] = {}
    if names_mtime:
        names = json.loads(Path(names_path).read_text(encoding="utf-8"))
    out = []
    for u in raw:
        c = u.get("coordinates") or {}
        if not u.get("union_id") or c.get("lat") is None:
            continue
        out.append({"union_id": u["union_id"], "name_en": u.get("union_name_en") or "?",
                    "name_bn": names.get(u["union_id"]) or names.get(u.get("union_name_en") or ""),
                    "upazila_en": u.get("upazila_name_en"), "lat": c["lat"], "lon": c["lon"]})
    out.sort(key=lambda x: (x["upazila_en"] or "", x["name_en"]))
    return tuple(out)


def unions() -> tuple[dict[str, Any], ...]:
    p = settings.AOI_OUT / "union_summary.json"
    if not p.exists():
        return ()
    n = settings.DATA / "union_names_bn.json"
    return _unions(str(p), p.stat().st_mtime, str(n), n.stat().st_mtime if n.exists() else 0.0)


def union_by_id(union_id: str | None) -> dict[str, Any] | None:
    if not union_id:
        return None
    return next((u for u in unions() if u["union_id"] == union_id), None)
