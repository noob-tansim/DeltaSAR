"""Shared test set-up: an empty in-memory database per test, no background loop, fake radar inputs.

The radar rule normally reads raster files written by jobs/j1. Tests replace that reader with a table of
distances, so they run without any data on disk.
"""
from __future__ import annotations

import datetime as dt
import os

os.environ["TICK_S"] = "0"
# TEST_DATABASE_URL=postgresql://... runs the same tests on Postgres (as on Supabase); default: in-memory SQLite
TEST_DB = os.environ.get("TEST_DATABASE_URL")
os.environ["DATABASE_URL"] = TEST_DB or "sqlite:///:memory:"
os.environ["CONSOLE_TOKEN"] = "test-token"
for _k in ("APPROVAL_WINDOW_S", "RETRY_AFTER_S", "MAX_RETRIES", "RIVER_MAX_AGE_H", "RADAR_MAX_AGE_D",
           "VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY", "SMTP_HOST"):
    os.environ.pop(_k, None)

import pytest  # noqa: E402

from src.alerts import db, inputs  # noqa: E402
from src.alerts.inputs import PassInfo, RadarInput  # noqa: E402

UTC = dt.timezone.utc
HOME = (24.69, 89.75)            # inside the covered area


def utc(y: int, mo: int, d: int, h: int = 0, mi: int = 0) -> dt.datetime:
    return dt.datetime(y, mo, d, h, mi, tzinfo=UTC)


def make_pass(track: str, date: str, acquired: dt.datetime, published: dt.datetime, *, baseline: bool = False,
              unknown_pct: float = 0.4) -> PassInfo:
    return PassInfo(track=track, date=date, acquired_utc=acquired, published_utc=published,
                    publication_source="test", granule_id=f"G_{track}_{date}", cmr_id=f"C_{track}_{date}",
                    processing_level="L2 GCOV PROVISIONAL (test)", unknown_pct=unknown_pct, is_baseline=baseline,
                    baseline={} if baseline else {"date": "20260618", "granule_id": "G_base"},
                    threshold_db=-15.62, threshold_method="test", tested_at_db=(-16.62, -15.62, -14.62),
                    new_water_km2={} if baseline else {"strict": 300.0, "mid": 400.0, "loose": 560.0},
                    range_within_25pct=None if baseline else False,
                    files={} if baseline else {"strict": "s.tif", "mid": "m.tif", "loose": "l.tif"})


PASSES = (
    make_pass("069A", "20260618", utc(2026, 6, 18, 23, 21), utc(2026, 7, 9, 1, 18), baseline=True),
    make_pass("069A", "20260712", utc(2026, 7, 12, 23, 21), utc(2026, 7, 19, 14, 40)),
    make_pass("069A", "20260724", utc(2026, 7, 24, 23, 21), utc(2026, 7, 27, 7, 21)),
    make_pass("069A", "20260817", utc(2026, 8, 17, 23, 21), utc(2026, 8, 23, 0, 58)),
)


@pytest.fixture(autouse=True)
def fresh_db():
    if TEST_DB:
        eng = db.init_engine(TEST_DB)
        db.Base.metadata.drop_all(eng)
        db.Base.metadata.create_all(eng)
    else:
        db.init_engine("sqlite:///:memory:")
    yield


@pytest.fixture()
def session():
    with db.session_scope() as s:
        yield s


@pytest.fixture()
def fake_radar(monkeypatch):
    """Radar inputs from a dict {(lat, lon): (d_strict, d_mid, d_loose)} instead of raster files."""
    table: dict[tuple[float, float], tuple[float | None, float | None, float | None]] = {}
    monkeypatch.setattr(inputs, "radar_passes", lambda: PASSES)
    monkeypatch.setattr(inputs, "radar_index_meta", lambda: {"min_patch_ha": 1.0})

    def radar_for(lat: float, lon: float, as_of: dt.datetime) -> RadarInput:
        p = inputs.latest_pass(as_of)
        if p is None or p.is_baseline:
            return RadarInput(p, True, False)
        ds, dm, dl = table.get((lat, lon), (None, None, None))
        return RadarInput(p, True, False, ds, dm, dl, None, None)

    monkeypatch.setattr(inputs, "radar_for", radar_for)
    return table


def add_person(s, device: str = "device-0001", lat: float = HOME[0], lon: float = HOME[1], **kw):
    from src.alerts.db import Person, utcnow
    fields = dict(device_id=device, display_name=device, union_id=None, home_lat=lat, home_lon=lon,
                  months=list(range(1, 13)), rain_on=True, rain_mm=76, river_on=True, radar_on=True, radar_km=1.0,
                  channels=["in_app"], mode={}, is_demo=True, consent_utc=utcnow())
    fields.update(kw)
    p = Person(**fields)
    s.add(p)
    s.flush()
    return p
