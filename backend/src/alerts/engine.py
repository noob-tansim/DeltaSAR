"""tick(): look at the inputs as of the clock, run the three rules for every person, turn fired rules into drafts.

One draft (alert_event) per rule and event, with one recipient row per person. A draft that was already
approved or rejected is never re-drafted inside the same scope, so nobody gets the same alert twice.
"""
from __future__ import annotations

import datetime as dt
import subprocess
import threading
from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.alerts import clock as clock_mod
from src.alerts import inputs, ledger, messages, rules, settings
from src.alerts.clock import Clock
from src.alerts.db import AlertEvent, AlertRecipient, Person, Setting
from src.alerts.rules import PersonCfg, RuleResult
from src.alerts.types import (DB_MAX, DB_MIN, RAIN_DATA_MAX_MM, RAIN_DATA_MIN_MM, RIVER_MAX_M, RIVER_MIN_M,
                              EventState, RuleName)
from src.config import NISAR_GAP_UTC, ROOT

LOCK = threading.Lock()                 # one tick / one state change at a time inside this process
_LAST: dict[str, Any] = {"utc": None, "rules": []}


def code_version() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return "not-in-git"


_CODE_VERSION = code_version()


def person_cfg(p: Person) -> PersonCfg:
    return PersonCfg(p.id, p.home_lat, p.home_lon, tuple(p.months), p.rain_on, p.rain_mm, p.river_on, p.radar_on,
                     p.radar_km)


def evaluate_person(s: Session, p: Person, as_of: dt.datetime) -> dict[RuleName, RuleResult]:
    cfg = person_cfg(p)
    radar_in = inputs.radar_for(cfg.lat, cfg.lon, as_of)
    river_in = inputs.river_for(s, inputs.station_for(cfg.lat, cfg.lon), as_of)
    rain_in = inputs.rain_for(s, as_of)
    return {
        RuleName.radar: rules.radar_rule(radar_in, cfg, as_of),
        RuleName.river: rules.river_rule(river_in, cfg, as_of),
        RuleName.rain: rules.rain_rule(rain_in, cfg, as_of),
    }


# ---------------------------------------------------------------- receipts
def _limits() -> list[str]:
    return [
        "Radar data carries its maturity label (PROVISIONAL or VALIDATED) from NASA.",
        f"No NISAR data {NISAR_GAP_UTC[0][:10]} to {NISAR_GAP_UTC[1][:10]}: shown as a gap, never filled.",
        settings.NOT_OFFICIAL_EN,
    ]


def build_receipt(rule: RuleName, ck: Clock, res: RuleResult) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """(receipt, input checks) for one fired rule. Every number on an alert can be traced through this."""
    base: dict[str, Any] = {"rule": rule.value, "rule_version": settings.RULE_VERSION, "code_version": _CODE_VERSION,
                            "as_of_utc": ck.as_of.isoformat(), "replay": ck.replay, "scope": ck.scope}
    checks: list[dict[str, Any]] = []
    v = res.values
    if rule == RuleName.radar:
        ps = next(p for p in inputs.radar_passes() if p.key == res.event_key)
        age_d = (ck.as_of - ps.acquired_utc).total_seconds() / 86400.0
        base["input"] = {
            "granule_id": ps.granule_id, "cmr_id": ps.cmr_id, "track": ps.track,
            "acquired_utc": ps.acquired_utc.isoformat(), "published_utc": ps.published_utc.isoformat(),
            "publication_source": ps.publication_source, "processing_level": ps.processing_level,
            "baseline_date": ps.baseline.get("date"), "baseline_granule_id": ps.baseline.get("granule_id"),
        }
        base["method"] = {
            "water_rule": f"HH < {ps.threshold_db} dB after a 3x3 median filter",
            "threshold_method": ps.threshold_method, "tested_at_db": list(ps.tested_at_db),
            "new_water": "water in this pass that was land in the baseline pass of the same track",
            "min_patch_ha": inputs.radar_index_meta().get("min_patch_ha"),
            "sure_means": "new water is inside the person's distance at T and at T - 1 dB",
        }
        km2 = ps.new_water_km2
        base["aoi_result"] = {"new_water_km2_range": [km2.get("strict"), km2.get("loose")],
                              "new_water_km2_mid": km2.get("mid"), "range_within_25pct": ps.range_within_25pct,
                              "unknown_pixel_pct": ps.unknown_pct}
        checks = [
            {"name": "backscatter", "value": f"{ps.unknown_pct:g}% of pixels outside the range (masked as unknown)",
             "allowed": f"{DB_MIN:g} to {DB_MAX:g} dB; at most {settings.RADAR_MAX_UNKNOWN_PCT:g}% unknown",
             "ok": ps.unknown_pct <= settings.RADAR_MAX_UNKNOWN_PCT},
            {"name": "picture age", "value": f"{age_d:.1f} days", "allowed": f"at most {settings.RADAR_MAX_AGE_D:g} days",
             "ok": age_d <= settings.RADAR_MAX_AGE_D},
            {"name": "published before as-of", "value": ps.published_utc.isoformat(timespec="minutes"),
             "allowed": f"at or before {ck.as_of.isoformat(timespec='minutes')}", "ok": ps.published_utc <= ck.as_of},
            {"name": "same track as baseline", "value": ps.track, "allowed": "one track per comparison", "ok": True},
        ]
    elif rule == RuleName.river:
        base["input"] = {k: v.get(k) for k in ("station", "level_m", "kind", "lead_days", "valid_local", "source_url",
                                               "entered_by")}
        base["method"] = {"line": f"danger level - {settings.RIVER_LINE_BELOW_DL_M:.2f} m",
                          "danger_level_m": v.get("danger_level_m"), "line_m": v.get("line_m"),
                          "danger_level_source": "FFWC public table (data/stations.json)"}
        checks = [
            {"name": "river level", "value": f"{v.get('level_m')} m", "allowed": f"{RIVER_MIN_M:g} to {RIVER_MAX_M:g} m",
             "ok": True},
            {"name": "reading age", "value": "inside the limit", "allowed": f"at most {settings.RIVER_MAX_AGE_H:g} h", "ok": True},
            {"name": "forecast lead", "value": f"{v.get('lead_days')} days",
             "allowed": f"at most {settings.RIVER_MAX_LEAD_DAYS} days", "ok": True},
        ]
    else:
        base["input"] = {k: v.get(k) for k in ("rain_mm", "date", "source")}
        base["method"] = {"rule": "24-hour total at or above the person's own level",
                          "area": "one value for the whole covered area (see source)"}
        checks = [
            {"name": "rain, 24 h", "value": f"{v.get('rain_mm')} mm",
             "allowed": f"{RAIN_DATA_MIN_MM:g} to {RAIN_DATA_MAX_MM:g} mm", "ok": True},
            {"name": "value age", "value": "inside the limit", "allowed": f"at most {settings.RAIN_MAX_AGE_D:g} days", "ok": True},
        ]
    base["limits"] = _limits()
    return base, checks


# ---------------------------------------------------------------- tick
def _note_inputs(s: Session, ck: Clock) -> None:
    """Write one `input_seen` row the first time a new pass / reading / rain day is visible in this scope."""
    seen: dict[str, str] = {}
    ps = inputs.latest_pass(ck.as_of)
    if ps:
        seen["radar"] = ps.key
    rn = inputs.rain_for(s, ck.as_of)
    if rn:
        seen["rain"] = rn.date
    for st in inputs.stations():
        rd = inputs.river_for(s, st, ck.as_of).reading
        if rd:
            seen[f"river:{st.name}"] = rd.issued_utc.isoformat()
    for name, key in seen.items():
        skey = f"seen:{ck.scope}:{name}"
        row = s.get(Setting, skey)
        if row is None or row.value != key:
            if row is None:
                s.add(Setting(key=skey, value=key))
            else:
                row.value = key
            ledger.write(s, ck.scope, "input_seen", payload={"input": name, "key": key, "as_of_utc": ck.as_of.isoformat()})


def _group(rule: RuleName, key: str) -> str:
    """Drafts of one group replace each other: all radar passes; one river station; all rain days."""
    return key.rsplit("_", 1)[0] if rule == RuleName.river else rule.value


def _supersede_older(s: Session, ck: Clock, rule: RuleName, key: str, new_id: str) -> None:
    """A newer event of the same kind makes an undecided older draft pointless: reject it, with the reason."""
    q = select(AlertEvent).where(AlertEvent.scope == ck.scope, AlertEvent.rule == rule.value, AlertEvent.id != new_id,
                                 AlertEvent.state.in_((EventState.drafted.value, EventState.late.value)))
    for old in s.scalars(q):
        if _group(rule, old.event_key) != _group(rule, key):
            continue
        old.state = EventState.rejected.value
        old.approved_by = "system"
        old.rejected_reason = f"replaced by a newer {rule.value} event ({key}) before anyone decided"
        ledger.write(s, ck.scope, "rejected", event_id=old.id, actor="system",
                     payload={"reason": old.rejected_reason, "superseded_by": new_id})


def tick(s: Session, ck: Clock | None = None) -> dict[str, Any]:
    """Evaluate all rules for all people at the clock's as-of time and create or extend drafts."""
    with LOCK:
        ck = ck or clock_mod.read(s)
        _note_inputs(s, ck)
        people = list(s.scalars(select(Person).where(Person.scope == ck.people_scope)))
        fired: dict[tuple[RuleName, str], list[tuple[Person, RuleResult]]] = {}
        reasons: dict[RuleName, Counter[str]] = {r: Counter() for r in RuleName}
        for p in people:
            for rule, res in evaluate_person(s, p, ck.as_of).items():
                reasons[rule][res.reason] += 1
                if res.fired and res.event_key:
                    fired.setdefault((rule, res.event_key), []).append((p, res))

        drafts = added = 0
        for (rule, key), hits in fired.items():
            ev = s.scalars(select(AlertEvent).where(AlertEvent.scope == ck.scope, AlertEvent.rule == rule.value,
                                                    AlertEvent.event_key == key)).first()
            if ev is None:
                receipt, checks = build_receipt(rule, ck, hits[0][1])
                sb, se = messages.event_summary(rule, len(hits), hits[0][1].values, ck.replay)
                ev = AlertEvent(scope=ck.scope, rule=rule.value, event_key=key, as_of_utc=ck.as_of, replay=ck.replay,
                                state=EventState.drafted.value, evidence=receipt, input_checks=checks,
                                message_bn=sb, message_en=se)
                s.add(ev)
                s.flush()
                drafts += 1
                ledger.write(s, ck.scope, "draft_created", event_id=ev.id,
                             payload={"rule": rule.value, "event_key": key, "recipients": len(hits)})
                _supersede_older(s, ck, rule, key, ev.id)
                is_new = True
            elif ev.state in (EventState.drafted.value, EventState.late.value):
                is_new = False
            else:
                continue                      # already decided in this scope: never re-draft
            have = {r.person_id for r in ev.recipients}
            here = 0
            for p, res in hits:
                if p.id in have:
                    continue
                mb, me = messages.render(rule, res.values, res.confidence, ck.replay)
                s.add(AlertRecipient(alert_event_id=ev.id, person_id=p.id, values=res.values,
                                     confidence=res.confidence.value, message_bn=mb, message_en=me))
                if not is_new:
                    here += 1
                    ledger.write(s, ck.scope, "recipient_added", event_id=ev.id, person_id=p.id)
            s.flush()
            if here:
                added += here
                sb, se = messages.event_summary(rule, len(have) + here, hits[0][1].values, ck.replay)
                ev.message_bn, ev.message_en = sb, se

        report = [{"rule": r.value, "people_checked": len(people), "fired": reasons[r].get("fired", 0),
                   "reasons": dict(reasons[r])} for r in RuleName]
        ledger.write(s, ck.scope, "rule_evaluated",
                     payload={"as_of_utc": ck.as_of.isoformat(), "people": len(people), "rules": report})
        _LAST.update(utc=dt.datetime.now(dt.timezone.utc), rules=report)
        return {"as_of_utc": ck.as_of, "replay": ck.replay, "drafts_created": drafts, "recipients_added": added,
                "rules": report}


def last_report() -> dict[str, Any]:
    return dict(_LAST)
