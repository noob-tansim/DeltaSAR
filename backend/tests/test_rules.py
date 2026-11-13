"""Boundary tests of the three rules. The rules are pure functions, so no database is needed."""
from __future__ import annotations

import datetime as dt

import pytest

from src.alerts import rules
from src.alerts.inputs import RadarInput, RainInput, Reading, RiverInput, Station
from src.alerts.rules import PersonCfg
from src.alerts.types import Confidence
from tests.conftest import PASSES, make_pass, utc

AS_OF = utc(2026, 7, 27, 8, 0)                    # 14:00 in Dhaka, July
P = PersonCfg("p1", 24.69, 89.75, months=(6, 7, 8, 9, 10))
PASS = PASSES[2]                                  # 24 Jul, published 27 Jul 07:21


# ---------------------------------------------------------------- rain
def rain(mm: float, date: str = "2026-07-26", source: str = "NASA IMERG") -> RainInput:
    return RainInput(date, mm, source, AS_OF)


@pytest.mark.parametrize("mm,fired", [(75.0, False), (75.2, False), (75.99, False), (76.0, True), (77.0, True)])
def test_rain_boundary_at_76mm(mm, fired):
    assert rules.rain_rule(rain(mm), P, AS_OF).fired is fired


def test_rain_uses_the_persons_own_level():
    p60 = PersonCfg("p", 24.69, 89.75, months=(7,), rain_mm=60)
    assert rules.rain_rule(rain(69.1), p60, AS_OF).fired is True
    assert rules.rain_rule(rain(69.1), P, AS_OF).fired is False


def test_rain_month_not_chosen():
    r = rules.rain_rule(rain(200), PersonCfg("p", 24.69, 89.75, months=(6, 8)), AS_OF)
    assert not r.fired and "month" in r.reason


def test_rain_rule_switched_off():
    r = rules.rain_rule(rain(200), PersonCfg("p", 24.69, 89.75, months=(7,), rain_on=False), AS_OF)
    assert not r.fired and "switched off" in r.reason


@pytest.mark.parametrize("mm", [501.0, -1.0, 9999.0])
def test_rain_outside_the_data_range_is_unknown_not_a_fire(mm):
    r = rules.rain_rule(rain(mm), P, AS_OF)
    assert not r.fired and "unknown" in r.reason


def test_rain_value_too_old():
    r = rules.rain_rule(rain(120, date="2026-07-20"), P, AS_OF)
    assert not r.fired and "older" in r.reason


def test_no_rain_value():
    assert rules.rain_rule(None, P, AS_OF).reason == "no rain value"


def test_forecast_rain_is_less_sure():
    r = rules.rain_rule(rain(90, source="Open-Meteo forecast"), P, AS_OF)
    assert r.fired and r.confidence == Confidence.less_sure


# ---------------------------------------------------------------- river
KAZIPUR = Station("Kazipur", 14.80, 24.64, 89.65, 87, None)


def river(level: float, *, age_h: float = 1.0, lead: int = 0, kind: str = "observed") -> RiverInput:
    issued = AS_OF - dt.timedelta(hours=age_h)
    return RiverInput(KAZIPUR, Reading(level, kind, lead, issued + dt.timedelta(days=lead), issued, "http://x", "t"))


@pytest.mark.parametrize("level,fired", [(14.49, False), (14.50, True), (14.51, True), (14.80, True), (13.74, False)])
def test_river_boundary_at_danger_level_minus_030(level, fired):
    r = rules.river_rule(river(level), P, AS_OF)
    assert r.fired is fired
    assert r.values["line_m"] == 14.5


def test_river_line_has_no_float_noise():
    assert rules.river_line_m(14.80) == 14.5
    assert rules.river_line_m(12.90) == 12.6


@pytest.mark.parametrize("age_h,usable", [(23.9, True), (24.0, True), (24.1, False), (200.0, False)])
def test_river_reading_age_limit(age_h, usable):
    r = rules.river_rule(river(15.0, age_h=age_h), P, AS_OF)
    assert r.fired is usable
    if not usable:
        assert "older" in r.reason


@pytest.mark.parametrize("lead,usable", [(3, True), (4, False)])
def test_river_forecast_lead_limit(lead, usable):
    assert rules.river_rule(river(15.0, lead=lead, kind="forecast"), P, AS_OF).fired is usable


@pytest.mark.parametrize("level", [4.0, 26.0])
def test_river_level_outside_range_is_unknown(level):
    r = rules.river_rule(river(level), P, AS_OF)
    assert not r.fired and "unknown" in r.reason


def test_river_without_reading_or_station():
    assert rules.river_rule(RiverInput(KAZIPUR, None), P, AS_OF).reason == "no river reading"
    assert not rules.river_rule(RiverInput(None, None), P, AS_OF).fired


# ---------------------------------------------------------------- radar
def radar(d_mid, d_strict=None, d_loose=None, *, pass_=PASS, in_river=False, in_aoi=True) -> RadarInput:
    return RadarInput(pass_, in_aoi, in_river, d_strict, d_mid, d_loose)


@pytest.mark.parametrize("d,fired", [(990, True), (1000, True), (1010, False), (0, True), (5000, False)])
def test_radar_boundary_at_1km(d, fired):
    assert rules.radar_rule(radar(d, d), P, AS_OF).fired is fired


def test_radar_uses_the_persons_own_distance():
    p2 = PersonCfg("p", 24.69, 89.75, months=(7,), radar_km=2.0)
    assert rules.radar_rule(radar(1500, 1500), p2, AS_OF).fired is True
    assert rules.radar_rule(radar(1500, 1500), P, AS_OF).fired is False


def test_radar_sure_only_if_the_strict_threshold_agrees():
    assert rules.radar_rule(radar(800, 900), P, AS_OF).confidence == Confidence.sure
    assert rules.radar_rule(radar(800, 1400), P, AS_OF).confidence == Confidence.less_sure
    assert rules.radar_rule(radar(800, None), P, AS_OF).confidence == Confidence.less_sure


def test_radar_loose_threshold_alone_never_fires():
    r = rules.radar_rule(radar(1500, 2500, 300), P, AS_OF)
    assert not r.fired and "beyond" in r.reason


def test_radar_skips_with_a_reason():
    assert "river mask" in rules.radar_rule(radar(100, 100, in_river=True), P, AS_OF).reason
    assert "outside" in rules.radar_rule(radar(100, 100, in_aoi=False), P, AS_OF).reason
    assert "no new water" in rules.radar_rule(radar(None), P, AS_OF).reason
    assert "no radar pass" in rules.radar_rule(RadarInput(None, True, False), P, AS_OF).reason
    assert "baseline" in rules.radar_rule(RadarInput(PASSES[0], True, False), P, utc(2026, 6, 20)).reason


def test_radar_too_many_unknown_pixels():
    bad = make_pass("069A", "20260724", PASS.acquired_utc, PASS.published_utc, unknown_pct=5.1)
    assert "unknown" in rules.radar_rule(radar(100, 100, pass_=bad), P, AS_OF).reason


def test_radar_never_alerts_from_an_old_picture():
    late = PASS.acquired_utc + dt.timedelta(days=14, hours=1)
    r = rules.radar_rule(radar(100, 100), PersonCfg("p", 24.69, 89.75, months=tuple(range(1, 13))), late)
    assert not r.fired and "older" in r.reason


def test_radar_event_key_and_values():
    r = rules.radar_rule(radar(179, 300), P, AS_OF)
    assert r.event_key == "069A_20260724"
    assert r.values["distance_m"] == 179 and r.values["walk_minutes"] == 5 and r.values["picture_age_days"] == 2


@pytest.mark.parametrize("d,minutes", [(0, 5), (400, 5), (401, 10), (800, 10), (1000, 15), (4000, 50)])
def test_walk_minutes_rounds_up_to_five(d, minutes):
    assert rules.walk_minutes(d) == minutes


def test_month_uses_dhaka_time_not_utc():
    # 30 June 20:00 UTC is already 1 July 02:00 in Dhaka
    assert rules.local_month(utc(2026, 6, 30, 20, 0)) == 7
