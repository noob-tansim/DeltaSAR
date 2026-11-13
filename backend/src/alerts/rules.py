"""The three alert rules. Pure functions: (inputs, person, as_of) -> RuleResult. No database, no clock, no AI.

A rule can only say "fired" or "did not fire, because ...". It never sends anything: the engine turns a fired
rule into a draft, and a volunteer approves the draft.
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field
from typing import Any

from src.alerts import settings
from src.alerts.inputs import RadarInput, RainInput, RiverInput
from src.alerts.types import (DHAKA, RAIN_DATA_MAX_MM, RAIN_DATA_MIN_MM, RIVER_MAX_M, RIVER_MIN_M, Confidence,
                              RuleName)


@dataclass(frozen=True)
class PersonCfg:
    """The part of a person's settings the rules need."""
    id: str
    lat: float
    lon: float
    months: tuple[int, ...]
    rain_on: bool = True
    rain_mm: int = 76
    river_on: bool = True
    radar_on: bool = True
    radar_km: float = 1.0


@dataclass(frozen=True)
class RuleResult:
    rule: RuleName
    fired: bool
    reason: str                              # "fired" or why the rule did not fire / could not evaluate
    confidence: Confidence = Confidence.unknown
    event_key: str | None = None
    values: dict[str, Any] = field(default_factory=dict)


def local_month(as_of: dt.datetime) -> int:
    return as_of.astimezone(DHAKA).month


def walk_minutes(distance_m: float) -> int:
    """Walking time at 80 m per minute, rounded up to 5 minutes (people think in rough walking time)."""
    return max(5, int(math.ceil(distance_m / settings.WALK_M_PER_MIN / 5.0)) * 5)


def _precheck(rule: RuleName, switched_on: bool, p: PersonCfg, as_of: dt.datetime) -> RuleResult | None:
    if not switched_on:
        return RuleResult(rule, False, "rule switched off by the person")
    if local_month(as_of) not in p.months:
        return RuleResult(rule, False, "month not chosen by the person")
    return None


# ---------------------------------------------------------------- radar
def radar_rule(x: RadarInput, p: PersonCfg, as_of: dt.datetime) -> RuleResult:
    """New water (water now, land at the track's baseline pass) within the person's distance from home."""
    R = RuleName.radar
    if (pre := _precheck(R, p.radar_on, p, as_of)) is not None:
        return pre
    if not x.in_aoi:
        return RuleResult(R, False, "home outside the covered area")
    ps = x.pass_
    if ps is None:
        return RuleResult(R, False, "no radar pass published yet")
    age_d = (as_of - ps.acquired_utc).total_seconds() / 86400.0
    if age_d > settings.RADAR_MAX_AGE_D:
        return RuleResult(R, False, f"radar picture older than {settings.RADAR_MAX_AGE_D:g} days")
    if ps.is_baseline:
        return RuleResult(R, False, "newest pass is the baseline of its track: nothing to compare yet")
    if ps.unknown_pct > settings.RADAR_MAX_UNKNOWN_PCT:
        return RuleResult(R, False, f"more than {settings.RADAR_MAX_UNKNOWN_PCT:g}% of the pass is unknown")
    if x.in_river:
        return RuleResult(R, False, "home lies inside the permanent river mask")
    if x.d_mid is None:
        return RuleResult(R, False, "no new water in this pass")
    limit_m = p.radar_km * 1000.0
    values: dict[str, Any] = {
        "distance_m": int(round(x.d_mid)), "walk_minutes": walk_minutes(x.d_mid), "limit_m": int(round(limit_m)),
        "picture_age_days": int(age_d), "track": ps.track, "pass_date": ps.date,
        "pass_utc": ps.acquired_utc.isoformat(), "processing_level": ps.processing_level,
        "distance_strict_m": None if x.d_strict is None else int(round(x.d_strict)),
        "distance_loose_m": None if x.d_loose is None else int(round(x.d_loose)),
        "previous_pass_date": x.prev_pass_date,
        "previous_distance_m": None if x.prev_d_mid is None else int(round(x.prev_d_mid)),
        "grew_since_previous_pass": None if x.prev_pass_date is None else (x.prev_d_mid is None or x.d_mid < x.prev_d_mid),
    }
    if x.d_mid > limit_m:
        return RuleResult(R, False, "nearest new water is beyond the person's distance", values=values)
    # sure only if the stricter threshold (T - 1 dB) also puts water inside the person's distance
    conf = Confidence.sure if (x.d_strict is not None and x.d_strict <= limit_m) else Confidence.less_sure
    return RuleResult(R, True, "fired", conf, ps.key, values)


# ---------------------------------------------------------------- river
def river_line_m(danger_level_m: float) -> float:
    return round(danger_level_m - settings.RIVER_LINE_BELOW_DL_M, 2)


def river_rule(x: RiverInput, p: PersonCfg, as_of: dt.datetime) -> RuleResult:
    """Observed or forecast level (lead <= 3 days) at or above danger level - 0.30 m."""
    R = RuleName.river
    if (pre := _precheck(R, p.river_on, p, as_of)) is not None:
        return pre
    if x.station is None:
        return RuleResult(R, False, "no river station configured")
    rd = x.reading
    if rd is None:
        return RuleResult(R, False, "no river reading")
    if not (RIVER_MIN_M <= rd.level_m <= RIVER_MAX_M):
        return RuleResult(R, False, f"river level outside {RIVER_MIN_M:g} to {RIVER_MAX_M:g} m: treated as unknown")
    age_h = (as_of - rd.issued_utc).total_seconds() / 3600.0
    if age_h > settings.RIVER_MAX_AGE_H:
        return RuleResult(R, False, f"river reading older than {settings.RIVER_MAX_AGE_H:g} h")
    if rd.lead_days > settings.RIVER_MAX_LEAD_DAYS:
        return RuleResult(R, False, f"forecast lead longer than {settings.RIVER_MAX_LEAD_DAYS} days")
    line = river_line_m(x.station.danger_level_m)
    level = round(rd.level_m, 2)
    values: dict[str, Any] = {
        "station": x.station.name, "level_m": level, "danger_level_m": x.station.danger_level_m, "line_m": line,
        "kind": rd.kind, "lead_days": rd.lead_days, "valid_local": rd.valid_utc.astimezone(DHAKA).isoformat(),
        "source_url": rd.source_url, "entered_by": rd.entered_by,
    }
    if level < line:
        return RuleResult(R, False, "river level below the alert line", values=values)
    key = f"{x.station.name}_{rd.valid_utc.astimezone(DHAKA).date().isoformat()}"
    return RuleResult(R, True, "fired", Confidence.sure, key, values)


# ---------------------------------------------------------------- rain
def rain_rule(x: RainInput | None, p: PersonCfg, as_of: dt.datetime) -> RuleResult:
    """Newest 24-hour rain total at or above the person's level."""
    R = RuleName.rain
    if (pre := _precheck(R, p.rain_on, p, as_of)) is not None:
        return pre
    if x is None:
        return RuleResult(R, False, "no rain value")
    if not (RAIN_DATA_MIN_MM <= x.mm <= RAIN_DATA_MAX_MM):
        return RuleResult(R, False, f"rain value outside {RAIN_DATA_MIN_MM:g} to {RAIN_DATA_MAX_MM:g} mm: treated as unknown")
    day_end = dt.datetime.fromisoformat(x.date).replace(tzinfo=dt.timezone.utc) + dt.timedelta(days=1)
    if (as_of - day_end).total_seconds() / 86400.0 > settings.RAIN_MAX_AGE_D:
        return RuleResult(R, False, f"rain value older than {settings.RAIN_MAX_AGE_D:g} days")
    values: dict[str, Any] = {"rain_mm": round(x.mm, 1), "limit_mm": p.rain_mm, "date": x.date, "source": x.source}
    if x.mm < p.rain_mm:
        return RuleResult(R, False, "rain below the person's level", values=values)
    conf = Confidence.less_sure if "forecast" in x.source.lower() else Confidence.sure
    return RuleResult(R, True, "fired", conf, f"area_{x.date}", values)
