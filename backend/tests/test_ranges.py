"""Every typed input rejects one value below and one above its range."""
from __future__ import annotations

import datetime as dt

import pytest
from pydantic import ValidationError

from src.alerts.types import ClockIn, PersonIn, RiverReadingIn

OK = dict(home_lat=24.69, home_lon=89.75, consent=True)


def person(**kw):
    return PersonIn(**{**OK, **kw})


def test_person_defaults_are_valid():
    p = person()
    assert p.rain_mm == 76 and p.radar_km == 1.0 and p.months == [6, 7, 8, 9, 10]
    assert [c.value for c in p.channels] == ["in_app"]


@pytest.mark.parametrize("mm", [5, 9, 301, 305, 77, 151])
def test_rain_level_out_of_range_or_off_step(mm):
    with pytest.raises(ValidationError):
        person(rain_mm=mm)


@pytest.mark.parametrize("mm", [10, 75, 76, 80, 152, 300])
def test_rain_level_allowed(mm):
    assert person(rain_mm=mm).rain_mm == mm


@pytest.mark.parametrize("km", [0.19, 0.0, 5.01, 10])
def test_radar_distance_out_of_range(km):
    with pytest.raises(ValidationError):
        person(radar_km=km)


@pytest.mark.parametrize("months", [[0], [13], [], [6, 14]])
def test_months_out_of_range(months):
    with pytest.raises(ValidationError):
        person(months=months)


def test_months_are_sorted_and_unique():
    assert person(months=[9, 6, 6, 7]).months == [6, 7, 9]


@pytest.mark.parametrize("lat,lon", [(24.20, 89.75), (24.81, 89.75), (24.5, 89.45), (24.5, 89.92), (23.8, 90.4)])
def test_home_outside_the_covered_area_is_refused(lat, lon):
    with pytest.raises(ValidationError):
        person(home_lat=lat, home_lon=lon)


def test_consent_is_required():
    with pytest.raises(ValidationError):
        person(consent=False)


def test_email_channel_needs_an_address():
    with pytest.raises(ValidationError):
        person(channels=["email"])
    assert person(channels=["email"], email="a@b.org").email == "a@b.org"


@pytest.mark.parametrize("bad", ["not-an-email", "a@b", "@b.org"])
def test_bad_email(bad):
    with pytest.raises(ValidationError):
        person(email=bad)


def test_unknown_field_is_refused():
    with pytest.raises(ValidationError):
        person(is_demo=False)


def reading(**kw):
    base = dict(station="Kazipur", valid_local=dt.datetime(2026, 8, 9, 6, 0), level_m=13.74,
                source_url="http://old.ffwc.gov.bd/", entered_by="tester")
    return RiverReadingIn(**{**base, **kw})


@pytest.mark.parametrize("level", [4.99, 25.01, -1, 100])
def test_river_level_out_of_range(level):
    with pytest.raises(ValidationError):
        reading(level_m=level)


@pytest.mark.parametrize("level", [5.0, 14.5, 25.0])
def test_river_level_allowed(level):
    assert reading(level_m=level).level_m == level


def test_forecast_lead_limits():
    with pytest.raises(ValidationError):
        reading(kind="forecast", lead_days=6)
    with pytest.raises(ValidationError):
        reading(kind="observed", lead_days=1)
    assert reading(kind="forecast", lead_days=3).lead_days == 3


def test_issued_time_must_carry_a_timezone():
    with pytest.raises(ValidationError):
        reading(issued_utc=dt.datetime(2026, 8, 9, 0, 0))


def test_replay_needs_a_time():
    with pytest.raises(ValidationError):
        ClockIn(mode="replay")
    with pytest.raises(ValidationError):
        ClockIn(mode="replay", as_of_utc=dt.datetime(2026, 7, 27, 8, 0))       # naive
    assert ClockIn(mode="live").as_of_utc is None
