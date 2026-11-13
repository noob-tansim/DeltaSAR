"""Builders for what the API returns: a person's status, one alert, its evidence card, a console event."""
from __future__ import annotations

import datetime as dt
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.alerts import inputs, lifecycle, messages, rules, settings
from src.alerts.clock import Clock
from src.alerts.db import AlertEvent, AlertRecipient, Person
from src.alerts.engine import person_cfg
from src.alerts.types import DHAKA, Confidence, EventState, RuleName, Status

SOURCES = [
    "NISAR L2 GCOV radar (NASA and ISRO, ASF DAAC)",
    "IMERG rain (NASA GPM, through NASA SERVIR ClimateSERV)",
    "River level and danger level (FFWC, Bangladesh Water Development Board)",
    "Terrain: Copernicus GLO-30 and MERIT Hydro",
    "Unions: geoBoundaries (CC BY 3.0 IGO)",
]
SENT_STATES = (EventState.sent.value, EventState.closed.value)


def person_out(p: Person) -> dict[str, Any]:
    return {"device_id": p.device_id, "display_name": p.display_name, "union_id": p.union_id, "home_lat": p.home_lat,
            "home_lon": p.home_lon, "months": p.months, "rain_on": p.rain_on, "rain_mm": p.rain_mm,
            "river_on": p.river_on, "radar_on": p.radar_on, "radar_km": p.radar_km, "channels": p.channels,
            "email": p.email, "phone": p.phone, "mode": p.mode, "is_demo": p.is_demo,
            "has_push": bool(p.subscriptions), "created_utc": p.created_utc}


def alert_out(rec: AlertRecipient, ev: AlertEvent, person: Person) -> dict[str, Any]:
    return {
        "recipient_id": rec.id, "event_id": ev.id, "rule": ev.rule, "event_state": ev.state, "state": rec.state,
        "confidence": rec.confidence, "message_bn": rec.message_bn, "message_en": rec.message_en,
        "values": rec.values, "replay": ev.replay, "as_of_utc": ev.as_of_utc, "created_utc": ev.created_utc,
        "approved_by": ev.approved_by, "approved_utc": ev.approved_utc, "sent_utc": rec.sent_utc,
        "ack_utc": rec.ack_utc, "reply": rec.reply, "reply_utc": rec.reply_utc, "reply_via": rec.reply_via,
        "channels": person.channels, "not_official_bn": settings.NOT_OFFICIAL_BN,
        "not_official_en": settings.NOT_OFFICIAL_EN,
    }


def alerts_for(s: Session, person: Person, scope: str | None = None) -> list[tuple[AlertRecipient, AlertEvent]]:
    """Alerts that were actually sent to this person, newest first."""
    q = (select(AlertRecipient, AlertEvent).join(AlertEvent, AlertRecipient.alert_event_id == AlertEvent.id)
         .where(AlertRecipient.person_id == person.id, AlertEvent.state.in_(SENT_STATES))
         .order_by(AlertEvent.created_utc.desc()))
    if scope:
        q = q.where(AlertEvent.scope == scope)
    return [(r, e) for r, e in s.execute(q).all()]


def _active_alert(s: Session, person: Person, ck: Clock) -> tuple[AlertRecipient, AlertEvent] | None:
    for rec, ev in alerts_for(s, person, ck.scope):
        if abs((ck.as_of - ev.as_of_utc).total_seconds()) <= settings.ALERT_ACTIVE_H * 3600:
            return rec, ev
    return None


def build_status(s: Session, person: Person, ck: Clock) -> dict[str, Any]:
    cfg = person_cfg(person)
    as_of = ck.as_of
    reasons: list[str] = []
    limit_m = cfg.radar_km * 1000.0

    # radar
    x = inputs.radar_for(cfg.lat, cfg.lon, as_of)
    radar: dict[str, Any] | None = None
    radar_fresh = False
    near_watch = False
    if x.pass_ is not None:
        ps = x.pass_
        age_d = (as_of - ps.acquired_utc).total_seconds() / 86400.0
        stale = age_d > settings.RADAR_STALE_D
        radar_fresh = not stale
        if x.d_mid is None:
            conf = Confidence.sure if not ps.is_baseline else Confidence.unknown
        else:
            agree = (x.d_strict is not None and x.d_strict <= limit_m) == (x.d_mid <= limit_m)
            conf = Confidence.sure if agree else Confidence.less_sure
        radar = {
            "track": ps.track, "pass_utc": ps.acquired_utc,
            "pass_local": ps.acquired_utc.astimezone(DHAKA).isoformat(timespec="minutes"),
            "published_utc": ps.published_utc, "age_days": round(age_d, 1), "stale": stale,
            "processing_level": ps.processing_level,
            "new_water_distance_m": None if x.d_mid is None else int(round(x.d_mid)),
            "walk_minutes": None if x.d_mid is None else rules.walk_minutes(x.d_mid),
            "confidence": conf.value,
            "grew_since_previous_pass": None if (x.d_mid is None or x.prev_pass_date is None)
            else (x.prev_d_mid is None or x.d_mid < x.prev_d_mid),
            "next_expected_local_date": inputs.next_expected_local_date(as_of),
            "overlay_url": f"{settings.WEB_DATA_BASE}/ov/newwater_{ps.track}_{ps.date}.png" if not ps.is_baseline else None,
            "overlay_bounds": ps.overlay["bounds"] if ps.overlay else None,
        }
        if radar_fresh and x.d_mid is not None:
            if x.d_mid <= 2 * limit_m:
                near_watch = True
                reasons.append("new water within twice the person's distance")
            elif x.d_loose is not None and x.d_loose <= limit_m:
                near_watch = True
                reasons.append("new water inside the person's distance only at the loose threshold")

    # river
    st = inputs.station_for(cfg.lat, cfg.lon)
    river: dict[str, Any] | None = None
    river_fresh = False
    river_watch = False
    if st is not None:
        rd = inputs.river_for(s, st, as_of).reading
        line = rules.river_line_m(st.danger_level_m)
        if rd is None:
            river = {"station": st.name, "level_m": None, "danger_level_m": st.danger_level_m, "line_m": line,
                     "kind": None, "valid_local": None, "age_hours": None, "stale": True, "source_url": st.source_url}
        else:
            age_h = (as_of - rd.issued_utc).total_seconds() / 3600.0
            river_fresh = age_h <= settings.RIVER_MAX_AGE_H
            river = {"station": st.name, "level_m": round(rd.level_m, 2), "danger_level_m": st.danger_level_m,
                     "line_m": line, "kind": rd.kind,
                     "valid_local": rd.valid_utc.astimezone(DHAKA).isoformat(timespec="minutes"),
                     "age_hours": round(age_h, 1), "stale": not river_fresh, "source_url": rd.source_url}
            if river_fresh and rd.level_m >= st.danger_level_m - settings.RIVER_WATCH_BELOW_DL_M:
                river_watch = True
                reasons.append(f"river within {settings.RIVER_WATCH_BELOW_DL_M:.2f} m of the danger level")

    # rain
    rn = inputs.rain_for(s, as_of)
    rain: dict[str, Any] = {"date": None, "last_24h_mm": None, "limit_mm": person.rain_mm, "source": None, "stale": True}
    if rn is not None:
        day_end = dt.datetime.fromisoformat(rn.date).replace(tzinfo=dt.timezone.utc) + dt.timedelta(days=1)
        rain = {"date": rn.date, "last_24h_mm": round(rn.mm, 1), "limit_mm": person.rain_mm, "source": rn.source,
                "stale": (as_of - day_end).total_seconds() / 86400.0 > settings.RAIN_MAX_AGE_D}

    active = _active_alert(s, person, ck)
    if active is not None:
        status = Status.alert
        reasons.insert(0, "an approved alert is active")
    elif not radar_fresh and not river_fresh:
        status = Status.no_data
        reasons.insert(0, "no radar picture newer than "
                          f"{settings.RADAR_STALE_D:g} days and no river reading inside {settings.RIVER_MAX_AGE_H:g} h")
    elif near_watch or river_watch:
        status = Status.watch
    else:
        status = Status.calm
        reasons.append("nothing near the person's limits in the newest data")

    return {
        "as_of_utc": as_of, "replay": ck.replay, "status": status.value, "reasons": reasons, "covered": x.in_aoi,
        "in_radar_gap": inputs.in_radar_gap(as_of), "union": inputs.union_by_id(person.union_id), "radar": radar,
        "river": river, "rain": rain,
        "active_alert": alert_out(active[0], active[1], person) if active else None,
        "sources": SOURCES, "not_official": True,
    }


# ---------------------------------------------------------------- evidence card
def _overlays_for(ev: AlertEvent) -> list[dict[str, Any]]:
    """Map pictures for the evidence card. They are static files of the web app (jobs/build_web_data.py);
    the radar backscatter itself comes from NASA GIBS for the pass date (the phone draws that layer)."""
    if ev.rule != RuleName.radar.value:
        return []
    track, date = ev.event_key.split("_", 1)
    ps = next((p for p in inputs.radar_passes() if p.key == ev.event_key), None)
    if ps is None or ps.overlay is None:
        return []
    base, bounds, before = settings.WEB_DATA_BASE, ps.overlay["bounds"], ps.baseline.get("date")
    return [
        {"id": f"water_{before}_{track}", "label": f"Water at the baseline pass ({before})",
         "url": f"{base}/ov/water_{before}_{track}.png", "bounds": bounds},
        {"id": f"water_{date}_{track}", "label": f"Water at this pass ({date})",
         "url": f"{base}/ov/water_{date}_{track}.png", "bounds": bounds},
        {"id": f"new_water_{ps.key}", "label": f"New water, {date} against {before}",
         "url": f"{base}/ov/newwater_{track}_{date}.png", "bounds": bounds},
    ]


_BN_MONTHS = ["জানুয়ারি", "ফেব্রুয়ারি", "মার্চ", "এপ্রিল", "মে", "জুন", "জুলাই", "আগস্ট", "সেপ্টেম্বর", "অক্টোবর", "নভেম্বর", "ডিসেম্বর"]


def _local(iso: str | None) -> str:
    if not iso:
        return "?"
    return dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(DHAKA).strftime("%d %b %Y, %H:%M")


def _local_bn(iso: str | None) -> str:
    if not iso:
        return "?"
    t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(DHAKA)
    return messages.bn(f"{t.day} {_BN_MONTHS[t.month - 1]} {t.year}, {t:%H:%M}")


def evidence_out(rec: AlertRecipient, ev: AlertEvent, person: Person) -> dict[str, Any]:
    v, r = rec.values, ev.evidence
    sure_bn = {"sure": "নিশ্চিত", "less_sure": "পুরোপুরি নিশ্চিত নয়", "unknown": "জানা নেই"}[rec.confidence]
    sure_en = {"sure": "Sure", "less_sure": "Less sure", "unknown": "Unknown"}[rec.confidence]
    un = inputs.union_by_id(person.union_id)
    where_en = un["name_en"] if un else "your area"
    where_bn = (un.get("name_bn") or un["name_en"]) if un else "আপনার এলাকা"
    if ev.rule == RuleName.radar.value:
        km2 = r.get("aoi_result", {}).get("new_water_km2_range") or [None, None]
        what = ("রাডারে নতুন পানি", "New water seen by radar")
        where = (f"{where_bn}: বাড়ি থেকে {messages.bn(v['distance_m'])} মিটার",
                 f"{where_en}: {v['distance_m']} m from home")
        when = (_local_bn(v.get("pass_utc")), _local(v.get("pass_utc")))
        how = (f"{sure_bn}। পুরো এলাকায় নতুন পানি {messages.bn(km2[0])} থেকে {messages.bn(km2[1])} বর্গ কিমি।",
               f"{sure_en}. New water over the whole area: {km2[0]} to {km2[1]} km² (threshold ±1 dB). "
               f"Data: {v.get('processing_level')}.")
    elif ev.rule == RuleName.river.value:
        what = ("নদীর পানি বিপদসীমার কাছে", "River level near the danger level")
        where = (f"যমুনা, {messages.STATION_BN.get(v['station'], v['station'])} পয়েন্ট", f"Jamuna at {v['station']}")
        when = (_local_bn(v.get("valid_local")), _local(v.get("valid_local")))
        how = (f"{sure_bn}। পানি {messages.bn(v['level_m'])} মি, বিপদসীমা {messages.bn(v['danger_level_m'])} মি।",
               f"{sure_en}. Level {v['level_m']} m, danger level {v['danger_level_m']} m, alert line {v['line_m']} m (FFWC).")
    else:
        what = ("ভারী বৃষ্টি", "Heavy rain")
        where = (where_bn, where_en)
        when = (messages.bn(v.get("date", "?")), str(v.get("date", "?")))
        how = (f"{sure_bn}। {messages.bn(v['rain_mm'])} মিমি, আপনার সীমা {messages.bn(v['limit_mm'])} মিমি।",
               f"{sure_en}. {v['rain_mm']} mm against your level of {v['limit_mm']} mm. Source: {v.get('source')}.")
    labels = [("what", "কী দেখা গেছে", "What was seen", what), ("where", "কোথায়", "Where", where),
              ("when", "কবে", "When", when), ("how_sure", "কতটা নিশ্চিত", "How sure", how)]
    return {
        "recipient_id": rec.id, "rule": ev.rule,
        "rows": [{"key": k, "label_bn": lb, "label_en": le, "value_bn": val[0], "value_en": val[1]}
                 for k, lb, le, val in labels],
        "receipt": {**r, "this_person": {"values": v, "confidence": rec.confidence}},
        "overlays": _overlays_for(ev),
        "not_official_bn": settings.NOT_OFFICIAL_BN, "not_official_en": settings.NOT_OFFICIAL_EN,
    }


# ---------------------------------------------------------------- console
def event_out(s: Session, ev: AlertEvent) -> dict[str, Any]:
    recs = []
    for r in ev.recipients:
        p = s.get(Person, r.person_id)
        un = inputs.union_by_id(p.union_id) if p else None
        recs.append({"recipient_id": r.id, "person_id": r.person_id, "display_name": p.display_name if p else None,
                     "union_name": un["name_en"] if un else None, "confidence": r.confidence, "values": r.values,
                     "state": r.state, "retry_count": r.retry_count, "reply": r.reply, "reply_utc": r.reply_utc,
                     "reply_via": r.reply_via, "callback_done": r.callback_done,
                     "channels": p.channels if p else []})
    return {"event_id": ev.id, "rule": ev.rule, "event_key": ev.event_key, "scope": ev.scope, "state": ev.state,
            "replay": ev.replay, "as_of_utc": ev.as_of_utc, "created_utc": ev.created_utc,
            "seconds_left": lifecycle.seconds_left(ev), "message_bn": ev.message_bn, "message_en": ev.message_en,
            "approved_by": ev.approved_by, "approved_utc": ev.approved_utc, "rejected_reason": ev.rejected_reason,
            "evidence": ev.evidence, "input_checks": ev.input_checks, "recipients": recs}
