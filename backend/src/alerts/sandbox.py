"""Guided-demo sandboxes: one private copy of the alert loop per website visitor.

A sandbox has its own replay clock and its own demo people, placed at real union centre points whose real distance
to new water on the NISAR 24 Jul 2026 pass is known (deploy_data/<aoi>/demo_households.json). Every rule, draft,
approval, reply and ledger row is the production code path; only the scope differs ("sb-<id>").

Nothing here invents a measurement. The only simulated thing is the keypad answer of the demo households
(`simulate_household_replies`), which is labelled "simulated" in the ledger and on screen.
"""
from __future__ import annotations

import datetime as dt
import json
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.alerts import clock as clock_mod
from src.alerts import engine, inputs, ledger, lifecycle, service, settings
from src.alerts.db import AlertEvent, AlertRecipient, Delivery, Ledger, Person, PushSub, Setting, utcnow
from src.alerts.types import DHAKA, Channel, EventState, Reply, RuleName

UTC = dt.timezone.utc
START_UTC = dt.datetime(2026, 7, 26, 8, 0, tzinfo=UTC)          # 26 Jul 2026, 14:00 in Dhaka: before NASA published 24 Jul
GAP_RAIN_UTC = dt.datetime(2026, 8, 7, 12, 30, tzinfo=UTC)      # radar off; IMERG for 5 Aug (75.2 mm) has just become known
SEASON_START = dt.datetime(2026, 6, 1, tzinfo=UTC)
HOUSEHOLD_CHANNELS = [["in_app", "call_sim"], ["sms_sim"], ["in_app"], ["call_sim"], ["in_app", "sms_sim"]]
SIMULATED_ANSWERS = [("safe", "call_sim"), ("help", "sms_sim"), None]   # the third household never answers


class SandboxError(ValueError):
    pass


@lru_cache(maxsize=1)
def _households_file(path: str, mtime: float) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def households() -> dict[str, Any]:
    p = settings.AOI_OUT / "demo_households.json"
    if not p.exists():
        raise SandboxError("demo households are not built (run python -m jobs.build_backend_data)")
    return _households_file(str(p), p.stat().st_mtime)


def _union_id_near(lat: float, lon: float) -> str | None:
    us = inputs.unions()
    if not us:
        return None
    return min(us, key=lambda u: (u["lat"] - lat) ** 2 + (u["lon"] - lon) ** 2)["union_id"]


def _add_person(s: Session, scope: str, device: str, name: str, h: dict[str, Any], channels: list[str],
                mode: dict[str, Any] | None = None) -> Person:
    p = Person(device_id=device, scope=scope, display_name=name, union_id=h.get("union_id") or _union_id_near(h["lat"], h["lon"]),
               home_lat=h["lat"], home_lon=h["lon"], months=[6, 7, 8, 9, 10, 11], rain_on=True, rain_mm=76,
               river_on=True, radar_on=True, radar_km=1.0, channels=channels, mode=mode or {}, is_demo=True,
               consent_utc=utcnow())
    s.add(p)
    s.flush()
    return p


def _recent_count(s: Session) -> int:
    hour_ago = (utcnow() - dt.timedelta(hours=1)).isoformat()
    rows = s.scalars(select(Setting).where(Setting.key.like("sb-%:created"))).all()
    return sum(1 for r in rows if r.value >= hour_ago)


def create(s: Session) -> dict[str, Any]:
    if _recent_count(s) >= settings.SANDBOX_MAX_PER_HOUR:
        raise SandboxError("too many demos started in the last hour; please try again in a few minutes")
    sid = "sb-" + secrets.token_hex(5)
    hh = households()
    s.add(Setting(key=f"{sid}:created", value=utcnow().isoformat()))
    v = hh["visitor"]
    _add_person(s, sid, f"{sid}-you", f"Your phone ({v['union']})", v, ["in_app", "push"],
                {"listen": True, "vibrate_light": True})
    for i, h in enumerate(hh["households"], 1):
        _add_person(s, sid, f"{sid}-h{i}", f"Household {i}, {h['union']}", h, HOUSEHOLD_CHANNELS[(i - 1) % len(HOUSEHOLD_CHANNELS)])
    ck = clock_mod.set_replay(s, START_UTC, scope=sid)
    ledger.write(s, sid, "sandbox_created", actor="visitor",
                 payload={"as_of_utc": ck.as_of.isoformat(), "people": 1 + len(hh["households"])})
    return {"sandbox_id": sid, "visitor_device_id": f"{sid}-you", "as_of_utc": ck.as_of}


def _check(s: Session, sid: str) -> None:
    if not clock_mod.is_sandbox(sid) or s.get(Setting, f"{sid}:created") is None:
        raise SandboxError("this demo has expired or does not exist; start a new one")


def _event(s: Session, sid: str, event_id: str) -> AlertEvent:
    ev = s.get(AlertEvent, event_id)
    if ev is None or ev.scope != sid:
        raise SandboxError("no such alert in this demo")
    return ev


def join(s: Session, sid: str, device_id: str) -> Person:
    """A visitor's real phone joins the sandbox (QR code). It lives at the next household place near new water."""
    _check(s, sid)
    if not (8 <= len(device_id) <= 64):
        raise SandboxError("device_id must be 8 to 64 characters")
    existing = s.scalars(select(Person).where(Person.device_id == device_id)).first()
    if existing is not None:
        if existing.scope == sid:
            return existing
        if clock_mod.is_sandbox(existing.scope):           # move the phone from an older demo to this one
            existing.scope = sid
            s.flush()
            return existing
        raise SandboxError("this device already belongs to the live service")
    n = len(s.scalars(select(Person).where(Person.scope == sid, Person.device_id.like(f"{sid}-phone%"))).all())
    h = households()["visitor"]
    p = _add_person(s, sid, device_id, f"Scanned phone {n + 1} ({h['union']})", h, ["in_app", "push"],
                    {"listen": True, "vibrate_light": True})
    ledger.write(s, sid, "person_joined", person_id=p.id, actor="visitor", payload={"via": "qr"})
    return p


def set_clock(s: Session, sid: str, mode: str, as_of: dt.datetime | None) -> clock_mod.Clock:
    _check(s, sid)
    if mode == "live":
        ck = clock_mod.set_live(s, sid)
    else:
        if as_of is None:
            raise SandboxError("as_of_utc is needed for replay")
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=UTC)
        if not (SEASON_START <= as_of <= utcnow()):
            raise SandboxError("replay time must lie between 1 Jun 2026 and now")
        ck = clock_mod.set_replay(s, as_of, scope=sid)
    ledger.write(s, sid, "clock_set", actor="visitor", payload={"mode": ck.mode.value, "as_of_utc": ck.as_of.isoformat()})
    return ck


def next_event(s: Session, sid: str) -> tuple[clock_mod.Clock, str]:
    """Jump to one minute after the next NISAR pass publication (the moment the data first existed)."""
    _check(s, sid)
    ck = clock_mod.read(s, sid)
    if not ck.replay:
        raise SandboxError("next event works in replay only")
    nxt = [p for p in inputs.radar_passes() if p.published_utc > ck.as_of]
    if not nxt:
        raise SandboxError("no later radar pass in the archive")
    p = min(nxt, key=lambda q: q.published_utc)
    label = (f"NASA published the NISAR pass of {p.acquired_utc.astimezone(DHAKA):%d %b %Y} (track {p.track}) "
             f"{(p.published_utc - p.acquired_utc).total_seconds() / 3600:.0f} h after the satellite passed")
    ck = clock_mod.set_replay(s, p.published_utc + dt.timedelta(minutes=1), scope=sid)
    ledger.write(s, sid, "clock_set", actor="visitor", payload={"mode": "replay", "as_of_utc": ck.as_of.isoformat(), "jumped_to": label})
    return ck, label


def tick(s: Session, sid: str) -> dict[str, Any]:
    _check(s, sid)
    return engine.tick(s, clock_mod.read(s, sid))


def approve(s: Session, sid: str, event_id: str, volunteer: str) -> AlertEvent:
    _check(s, sid)
    _event(s, sid, event_id)
    with engine.LOCK:
        return lifecycle.approve(s, event_id, volunteer)


def reject(s: Session, sid: str, event_id: str, volunteer: str, reason: str) -> AlertEvent:
    _check(s, sid)
    _event(s, sid, event_id)
    with engine.LOCK:
        return lifecycle.reject(s, event_id, volunteer, reason)


def callback_done(s: Session, sid: str, recipient_id: str, volunteer: str) -> AlertRecipient:
    _check(s, sid)
    rec = s.get(AlertRecipient, recipient_id)
    if rec is None:
        raise SandboxError("no such recipient")
    _event(s, sid, rec.alert_event_id)
    with engine.LOCK:
        return lifecycle.callback_done(s, recipient_id, volunteer)


def simulate_household_replies(s: Session, sid: str) -> int:
    """Demo households answer by keypad (simulated, labelled): one presses 1, one presses 2, one stays silent."""
    _check(s, sid)
    n = 0
    q = (select(AlertRecipient).join(AlertEvent, AlertRecipient.alert_event_id == AlertEvent.id)
         .join(Person, AlertRecipient.person_id == Person.id)
         .where(AlertEvent.scope == sid, AlertEvent.state == EventState.sent.value, Person.device_id.like(f"{sid}-h%"))
         .order_by(Person.device_id))
    for i, rec in enumerate(s.scalars(q).all()):
        ans = SIMULATED_ANSWERS[i % len(SIMULATED_ANSWERS)]
        if ans is None or rec.reply is not None:
            continue
        person = s.get(Person, rec.person_id)
        assert person is not None
        with engine.LOCK:
            lifecycle.reply(s, rec.id, person.device_id, Reply(ans[0]), Channel(ans[1]))
        n += 1
    return n


# ---------------------------------------------------------------- snapshot for the guided-demo screen
def snapshot(s: Session, sid: str, since_id: int = 0) -> dict[str, Any]:
    _check(s, sid)
    ck = clock_mod.read(s, sid)
    people = s.scalars(select(Person).where(Person.scope == sid).order_by(Person.created_utc)).all()
    ppl = []
    for p in people:
        res = engine.evaluate_person(s, p, ck.as_of)
        un = inputs.union_by_id(p.union_id)
        ppl.append({
            "device_id": p.device_id, "display_name": p.display_name, "lat": p.home_lat, "lon": p.home_lon,
            "union": un["name_en"] if un else None, "union_bn": un.get("name_bn") if un else None,
            "channels": p.channels, "is_visitor": p.device_id == f"{sid}-you", "has_push": bool(p.subscriptions),
            "rules": {r.value: {"fired": x.fired, "reason": x.reason, "confidence": x.confidence.value,
                                "values": {k: v for k, v in x.values.items()
                                           if k in ("distance_m", "walk_minutes", "limit_m", "distance_strict_m",
                                                    "rain_mm", "limit_mm", "level_m", "line_m", "picture_age_days")}}
                      for r, x in res.items()},
        })
    events = s.scalars(select(AlertEvent).where(AlertEvent.scope == sid).order_by(AlertEvent.created_utc.desc()).limit(10)).all()
    rows = s.scalars(select(Ledger).where(Ledger.scope == sid, Ledger.id > since_id).order_by(Ledger.id.desc()).limit(60)).all()
    ps = inputs.latest_pass(ck.as_of)
    rn = inputs.rain_for(s, ck.as_of)
    nxt = [p for p in inputs.radar_passes() if p.published_utc > ck.as_of] if ck.replay else []
    nxt_p = min(nxt, key=lambda q: q.published_utc) if nxt else None
    return {
        "sandbox_id": sid, "mode": ck.mode.value, "replay": ck.replay, "as_of_utc": ck.as_of,
        "as_of_local": ck.as_of.astimezone(DHAKA).isoformat(timespec="minutes"),
        "in_radar_gap": inputs.in_radar_gap(ck.as_of),
        "next_pass": None if nxt_p is None else {"date": nxt_p.date, "track": nxt_p.track,
                                                  "published_utc": nxt_p.published_utc, "acquired_utc": nxt_p.acquired_utc},
        "radar": None if ps is None else {
            "key": ps.key, "track": ps.track, "date": ps.date, "acquired_utc": ps.acquired_utc,
            "published_utc": ps.published_utc, "processing_level": ps.processing_level, "is_baseline": ps.is_baseline,
            "age_days": round((ck.as_of - ps.acquired_utc).total_seconds() / 86400.0, 1),
            "new_water_km2": ps.new_water_km2, "latency_h": round((ps.published_utc - ps.acquired_utc).total_seconds() / 3600, 1)},
        "rain": None if rn is None else {"date": rn.date, "mm": rn.mm, "source": rn.source},
        "people": ppl,
        "events": [service.event_out(s, e) for e in events],
        "ledger": [{"id": r.id, "utc": r.utc, "kind": r.kind, "actor": r.actor, "person_id": r.person_id,
                    "payload": r.payload} for r in rows],
        "impact": ledger.impact(s, sid),
        "approval_window_s": settings.APPROVAL_WINDOW_S,
    }


# ---------------------------------------------------------------- housekeeping
def purge_expired(s: Session) -> int:
    """Remove sandboxes older than SANDBOX_TTL_H (people, alerts, deliveries, clock). Ledger rows stay (no contact data)."""
    limit = (utcnow() - dt.timedelta(hours=settings.SANDBOX_TTL_H)).isoformat()
    old = [r.key.split(":")[0] for r in s.scalars(select(Setting).where(Setting.key.like("sb-%:created"))) if r.value < limit]
    for sid in old:
        ev_ids = list(s.scalars(select(AlertEvent.id).where(AlertEvent.scope == sid)))
        if ev_ids:
            rec_ids = list(s.scalars(select(AlertRecipient.id).where(AlertRecipient.alert_event_id.in_(ev_ids))))
            if rec_ids:
                s.execute(delete(Delivery).where(Delivery.alert_recipient_id.in_(rec_ids)))
                s.execute(delete(AlertRecipient).where(AlertRecipient.id.in_(rec_ids)))
            s.execute(delete(AlertEvent).where(AlertEvent.id.in_(ev_ids)))
        p_ids = list(s.scalars(select(Person.id).where(Person.scope == sid)))
        if p_ids:
            s.execute(delete(PushSub).where(PushSub.person_id.in_(p_ids)))
            s.execute(delete(Person).where(Person.id.in_(p_ids)))
        s.execute(delete(Setting).where(Setting.key.like(f"{sid}:%")))
        s.execute(delete(Setting).where(Setting.key.like(f"seen:{sid}:%")))
    s.flush()
    return len(old)


def rule_names() -> list[str]:
    return [r.value for r in RuleName]
