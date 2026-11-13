"""API of the alert layer: phone routes and volunteer-console routes. Mounted on the kit's app by install()."""
from __future__ import annotations

import datetime as dt
import threading
import time
from typing import Any, Iterator

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.alerts import clock as clock_mod
from src.alerts import engine, inputs, ledger, lifecycle, service, settings
from src.alerts.db import (AlertEvent, AlertRecipient, Ledger, Person, PushSub, RiverReading, get_session, init_engine,
                           session_scope, utcnow)
from src.alerts.types import (DHAKA, RAIN_DATA_MAX_MM, RAIN_DATA_MIN_MM, RIVER_MAX_M, RIVER_MIN_M, AckIn, AlertOut,
                              ApproveIn, CallbackIn, ClockIn, ClockMode, ClockOut, EventOut, EventState, EvidenceOut,
                              ImpactOut, InputCheck, InputsOut, LedgerRow, PersonIn, PersonOut, PushSubscribeIn,
                              RainOut, RejectIn, ReplyIn, RiverReadingIn, RiverReadingOut, StatusOut, TickOut,
                              UnionOut)
from src.config import ROOT

def db() -> Iterator[Session]:
    yield from get_session()


def require_console(authorization: str | None = Header(default=None)) -> None:
    if authorization != f"Bearer {settings.CONSOLE_TOKEN}":
        raise HTTPException(401, "console token missing or wrong")


router = APIRouter(prefix="/api/v1", tags=["phone"])
console = APIRouter(prefix="/api/v1/console", tags=["console"], dependencies=[Depends(require_console)])


def _person(s: Session, device_id: str) -> Person:
    p = s.scalars(select(Person).where(Person.device_id == device_id)).first()
    if p is None:
        raise HTTPException(404, "this device has not joined yet")
    return p


def _recipient(s: Session, recipient_id: str) -> tuple[AlertRecipient, AlertEvent, Person]:
    rec = s.get(AlertRecipient, recipient_id)
    if rec is None:
        raise HTTPException(404, "no such alert")
    ev, person = s.get(AlertEvent, rec.alert_event_id), s.get(Person, rec.person_id)
    if ev is None or person is None or ev.state not in service.SENT_STATES:
        raise HTTPException(404, "no such alert")      # drafts are never visible to a phone
    return rec, ev, person


# ================================================================ phone
@router.get("/unions", response_model=list[UnionOut])
def list_unions() -> Any:
    return list(inputs.unions())


@router.put("/people/{device_id}", response_model=PersonOut)
def put_person(device_id: str, body: PersonIn, s: Session = Depends(db)) -> Any:
    if not (8 <= len(device_id) <= 64):
        raise HTTPException(422, "device_id must be 8 to 64 characters")
    if body.union_id and inputs.union_by_id(body.union_id) is None:
        raise HTTPException(422, "unknown union_id")
    p = s.scalars(select(Person).where(Person.device_id == device_id)).first()
    fields = dict(display_name=body.display_name, union_id=body.union_id, home_lat=body.home_lat,
                  home_lon=body.home_lon, months=body.months, rain_on=body.rain_on, rain_mm=body.rain_mm,
                  river_on=body.river_on, radar_on=body.radar_on, radar_km=body.radar_km,
                  channels=[c.value for c in body.channels], email=body.email, phone=body.phone,
                  mode=body.mode.model_dump())
    if p is None:
        p = Person(device_id=device_id, is_demo=True, consent_utc=utcnow(), **fields)
        s.add(p)
    else:
        for k, v in fields.items():
            setattr(p, k, v)
    s.flush()
    return service.person_out(p)


@router.get("/people/{device_id}", response_model=PersonOut)
def get_person(device_id: str, s: Session = Depends(db)) -> Any:
    return service.person_out(_person(s, device_id))


@router.delete("/people/{device_id}")
def delete_person(device_id: str, s: Session = Depends(db)) -> dict[str, Any]:
    """Removes contact details and push subscriptions and switches every rule off. Past ledger rows stay (they hold no contact data)."""
    p = _person(s, device_id)
    p.email = p.phone = p.display_name = None
    p.channels = ["in_app"]
    p.rain_on = p.river_on = p.radar_on = False
    for sub in list(p.subscriptions):
        s.delete(sub)
    s.flush()
    return {"removed": True}


@router.get("/people/{device_id}/status", response_model=StatusOut)
def person_status(device_id: str, s: Session = Depends(db)) -> Any:
    p = _person(s, device_id)
    return service.build_status(s, p, clock_mod.for_person(s, p))


@router.get("/people/{device_id}/alerts", response_model=list[AlertOut])
def person_alerts(device_id: str, s: Session = Depends(db)) -> Any:
    p = _person(s, device_id)
    return [service.alert_out(r, e, p) for r, e in service.alerts_for(s, p)]


@router.get("/people/{device_id}/rain", response_model=RainOut)
def person_rain(device_id: str, s: Session = Depends(db)) -> Any:
    p = _person(s, device_id)
    ck = clock_mod.for_person(s, p)
    days = inputs.rain_days(s, ck.as_of, 7)
    return {"as_of_utc": ck.as_of, "replay": ck.replay, "days": [{"date": d.date, "mm": round(d.mm, 1)} for d in days],
            "limit_mm": p.rain_mm, "source": days[-1].source if days else None,
            "note": "One 24-hour total per day for the whole covered area (the wettest IMERG cell)."}


@router.get("/alerts/{recipient_id}", response_model=AlertOut)
def get_alert(recipient_id: str, s: Session = Depends(db)) -> Any:
    return service.alert_out(*_recipient(s, recipient_id))


@router.get("/alerts/{recipient_id}/evidence", response_model=EvidenceOut)
def get_evidence(recipient_id: str, s: Session = Depends(db)) -> Any:
    return service.evidence_out(*_recipient(s, recipient_id))


@router.post("/alerts/{recipient_id}/ack", response_model=AlertOut)
def post_ack(recipient_id: str, body: AckIn, s: Session = Depends(db)) -> Any:
    try:
        with engine.LOCK:
            lifecycle.ack(s, recipient_id, body.device_id)
    except lifecycle.LifecycleError as exc:
        raise HTTPException(409, str(exc))
    return service.alert_out(*_recipient(s, recipient_id))


@router.post("/alerts/{recipient_id}/reply", response_model=AlertOut)
def post_reply(recipient_id: str, body: ReplyIn, s: Session = Depends(db)) -> Any:
    try:
        with engine.LOCK:
            lifecycle.reply(s, recipient_id, body.device_id, body.reply, body.via)
    except lifecycle.LifecycleError as exc:
        raise HTTPException(409, str(exc))
    return service.alert_out(*_recipient(s, recipient_id))


@router.get("/push/public-key")
def push_public_key() -> dict[str, Any]:
    return {"public_key": settings.VAPID_PUBLIC_KEY or None, "enabled": bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)}


@router.post("/push/subscribe")
def push_subscribe(body: PushSubscribeIn, s: Session = Depends(db)) -> dict[str, Any]:
    p = _person(s, body.device_id)
    sub = s.scalars(select(PushSub).where(PushSub.endpoint == body.subscription.endpoint)).first()
    if sub is None:
        s.add(PushSub(person_id=p.id, endpoint=body.subscription.endpoint, p256dh=body.subscription.keys.p256dh,
                      auth=body.subscription.keys.auth, user_agent=body.user_agent))
    else:
        sub.person_id, sub.p256dh, sub.auth = p.id, body.subscription.keys.p256dh, body.subscription.keys.auth
    if "push" not in p.channels:
        p.channels = [*p.channels, "push"]
    s.flush()
    return {"subscribed": True}


# ================================================================ console
def _next_event(s: Session, as_of: dt.datetime) -> tuple[dt.datetime, str] | None:
    """Next moment after as_of at which an input changes: a radar pass is published or a river reading is issued."""
    cands: list[tuple[dt.datetime, str]] = []
    for p in inputs.radar_passes():
        if p.published_utc > as_of:
            cands.append((p.published_utc, f"NISAR pass of {p.date} (track {p.track}) published"))
    rd = s.scalars(select(RiverReading).where(RiverReading.issued_utc > as_of).order_by(RiverReading.issued_utc).limit(1)).first()
    if rd is not None:
        cands.append((rd.issued_utc, f"river reading issued for {rd.station}"))
    return min(cands) if cands else None


def _clock_out(s: Session) -> dict[str, Any]:
    ck = clock_mod.read(s)
    nxt = _next_event(s, ck.as_of) if ck.replay else None
    return {"mode": ck.mode, "as_of_utc": ck.as_of, "real_utc": utcnow(), "scope": ck.scope,
            "demo_timing": settings.DEMO_TIMING, "approval_window_s": settings.APPROVAL_WINDOW_S,
            "retry_after_s": settings.RETRY_AFTER_S, "max_retries": settings.MAX_RETRIES,
            "next_event_utc": nxt[0] if nxt else None, "next_event_label": nxt[1] if nxt else None}


@console.get("/clock", response_model=ClockOut)
def get_clock(s: Session = Depends(db)) -> Any:
    return _clock_out(s)


@console.put("/clock", response_model=ClockOut)
def put_clock(body: ClockIn, s: Session = Depends(db)) -> Any:
    if body.mode == ClockMode.live:
        ck = clock_mod.set_live(s)
    else:
        assert body.as_of_utc is not None
        ck = clock_mod.set_replay(s, body.as_of_utc, body.new_run)
    ledger.write(s, ck.scope, "clock_set", actor="console", payload={"mode": ck.mode.value, "as_of_utc": ck.as_of.isoformat()})
    return _clock_out(s)


@console.post("/clock/next-event", response_model=ClockOut)
def clock_next_event(s: Session = Depends(db)) -> Any:
    ck = clock_mod.read(s)
    if not ck.replay:
        raise HTTPException(409, "next-event works in REPLAY only")
    nxt = _next_event(s, ck.as_of)
    if nxt is None:
        raise HTTPException(409, "no later event in the archive")
    ck = clock_mod.set_replay(s, nxt[0] + dt.timedelta(minutes=1))
    ledger.write(s, ck.scope, "clock_set", actor="console",
                 payload={"mode": "replay", "as_of_utc": ck.as_of.isoformat(), "jumped_to": nxt[1]})
    return _clock_out(s)


@console.post("/tick", response_model=TickOut)
def post_tick(s: Session = Depends(db)) -> Any:
    out = engine.tick(s)
    with engine.LOCK:
        lifecycle.sweep(s)
    return out


@console.get("/drafts", response_model=list[EventOut])
def get_drafts(s: Session = Depends(db)) -> Any:
    ck = clock_mod.read(s)
    q = (select(AlertEvent).where(AlertEvent.scope == ck.scope,
                                  AlertEvent.state.in_((EventState.drafted.value, EventState.late.value)))
         .order_by(AlertEvent.created_utc.desc()))
    return [service.event_out(s, e) for e in s.scalars(q)]


@console.get("/events", response_model=list[EventOut])
def get_events(state: EventState | None = None, all_scopes: bool = False, limit: int = Query(50, ge=1, le=200),
               s: Session = Depends(db)) -> Any:
    ck = clock_mod.read(s)
    q = select(AlertEvent).order_by(AlertEvent.created_utc.desc()).limit(limit)
    if not all_scopes:
        q = q.where(AlertEvent.scope == ck.scope)
    if state is not None:
        q = q.where(AlertEvent.state == state.value)
    return [service.event_out(s, e) for e in s.scalars(q)]


@console.post("/drafts/{event_id}/approve", response_model=EventOut)
def approve(event_id: str, body: ApproveIn, s: Session = Depends(db)) -> Any:
    try:
        with engine.LOCK:
            ev = lifecycle.approve(s, event_id, body.volunteer)
    except lifecycle.LifecycleError as exc:
        raise HTTPException(409, str(exc))
    s.refresh(ev)
    return service.event_out(s, ev)


@console.post("/drafts/{event_id}/reject", response_model=EventOut)
def reject(event_id: str, body: RejectIn, s: Session = Depends(db)) -> Any:
    try:
        with engine.LOCK:
            ev = lifecycle.reject(s, event_id, body.volunteer, body.reason)
    except lifecycle.LifecycleError as exc:
        raise HTTPException(409, str(exc))
    return service.event_out(s, ev)


@console.post("/callbacks/{recipient_id}/done", response_model=EventOut)
def callback_done(recipient_id: str, body: CallbackIn, s: Session = Depends(db)) -> Any:
    try:
        with engine.LOCK:
            rec = lifecycle.callback_done(s, recipient_id, body.volunteer)
    except lifecycle.LifecycleError as exc:
        raise HTTPException(409, str(exc))
    ev = s.get(AlertEvent, rec.alert_event_id)
    assert ev is not None
    return service.event_out(s, ev)


@console.get("/ledger", response_model=list[LedgerRow])
def get_ledger(since_id: int = 0, kind: str | None = None, all_scopes: bool = False,
               limit: int = Query(100, ge=1, le=500), s: Session = Depends(db)) -> Any:
    ck = clock_mod.read(s)
    q = select(Ledger).where(Ledger.id > since_id).order_by(Ledger.id.desc()).limit(limit)
    if not all_scopes:
        q = q.where(Ledger.scope == ck.scope)
    if kind:
        q = q.where(Ledger.kind == kind)
    return [{"id": r.id, "utc": r.utc, "scope": r.scope, "kind": r.kind, "alert_event_id": r.alert_event_id,
             "person_id": r.person_id, "actor": r.actor, "payload": r.payload} for r in s.scalars(q)]


@console.get("/impact", response_model=ImpactOut)
def get_impact(scope: str | None = None, s: Session = Depends(db)) -> Any:
    return ledger.impact(s, scope or clock_mod.read(s).scope)


@console.get("/inputs", response_model=InputsOut)
def get_inputs(s: Session = Depends(db)) -> Any:
    ck = clock_mod.read(s)
    as_of = ck.as_of
    checks: list[dict[str, Any]] = []
    radar: dict[str, Any] | None = None
    ps = inputs.latest_pass(as_of)
    if ps is not None:
        age_d = (as_of - ps.acquired_utc).total_seconds() / 86400.0
        radar = {"track": ps.track, "date": ps.date, "acquired_utc": ps.acquired_utc, "published_utc": ps.published_utc,
                 "processing_level": ps.processing_level, "age_days": round(age_d, 1), "is_baseline": ps.is_baseline,
                 "new_water_km2": ps.new_water_km2, "range_within_25pct": ps.range_within_25pct,
                 "unknown_pct": ps.unknown_pct, "granule_id": ps.granule_id,
                 "in_radar_gap_now": inputs.in_radar_gap(as_of),
                 "next_expected_local_date": inputs.next_expected_local_date(as_of)}
        checks.append({"name": "radar picture age", "value": f"{age_d:.1f} days",
                       "allowed": f"at most {settings.RADAR_MAX_AGE_D:g} days for an alert", "ok": age_d <= settings.RADAR_MAX_AGE_D})
        checks.append({"name": "radar unknown pixels", "value": f"{ps.unknown_pct:g}%",
                       "allowed": f"at most {settings.RADAR_MAX_UNKNOWN_PCT:g}%", "ok": ps.unknown_pct <= settings.RADAR_MAX_UNKNOWN_PCT})
    else:
        checks.append({"name": "radar", "value": "no pass published yet", "allowed": "one published pass", "ok": False})
    river: list[dict[str, Any]] = []
    for st in inputs.stations():
        rd = inputs.river_for(s, st, as_of).reading
        row: dict[str, Any] = {"station": st.name, "danger_level_m": st.danger_level_m,
                               "line_m": round(st.danger_level_m - settings.RIVER_LINE_BELOW_DL_M, 2), "reading": None}
        if rd is not None:
            age_h = (as_of - rd.issued_utc).total_seconds() / 3600.0
            row["reading"] = {"level_m": rd.level_m, "kind": rd.kind, "lead_days": rd.lead_days,
                              "valid_local": rd.valid_utc.astimezone(DHAKA).isoformat(timespec="minutes"),
                              "issued_utc": rd.issued_utc, "age_hours": round(age_h, 1), "source_url": rd.source_url,
                              "entered_by": rd.entered_by}
            checks.append({"name": f"river level, {st.name}", "value": f"{rd.level_m:.2f} m",
                           "allowed": f"{RIVER_MIN_M:g} to {RIVER_MAX_M:g} m", "ok": RIVER_MIN_M <= rd.level_m <= RIVER_MAX_M})
            checks.append({"name": f"river reading age, {st.name}", "value": f"{age_h:.1f} h",
                           "allowed": f"at most {settings.RIVER_MAX_AGE_H:g} h", "ok": age_h <= settings.RIVER_MAX_AGE_H})
        else:
            checks.append({"name": f"river reading, {st.name}", "value": "none", "allowed": "one reading", "ok": False})
        river.append(row)
    rn = inputs.rain_for(s, as_of)
    rain: dict[str, Any] | None = None
    if rn is not None:
        rain = {"date": rn.date, "mm": rn.mm, "source": rn.source, "visible_utc": rn.visible_utc}
        checks.append({"name": "rain, 24 h", "value": f"{rn.mm:.1f} mm on {rn.date}",
                       "allowed": f"{RAIN_DATA_MIN_MM:g} to {RAIN_DATA_MAX_MM:g} mm", "ok": RAIN_DATA_MIN_MM <= rn.mm <= RAIN_DATA_MAX_MM})
    else:
        checks.append({"name": "rain", "value": "none", "allowed": "one daily total", "ok": False})
    last = engine.last_report()
    return {"as_of_utc": as_of, "replay": ck.replay, "radar": radar, "river": river, "rain": rain,
            "checks": [InputCheck(**c) for c in checks], "last_tick_utc": last.get("utc"), "rules": last.get("rules") or []}


@console.post("/river-readings", response_model=RiverReadingOut)
def add_river_reading(body: RiverReadingIn, s: Session = Depends(db)) -> Any:
    if body.station not in {st.name for st in inputs.stations()}:
        raise HTTPException(422, f"unknown station; use one of {[st.name for st in inputs.stations()]}")
    valid = body.valid_local if body.valid_local.tzinfo else body.valid_local.replace(tzinfo=DHAKA)
    valid_utc = valid.astimezone(dt.timezone.utc)
    ck = clock_mod.read(s)
    issued = body.issued_utc or (ck.as_of if ck.replay else utcnow())
    row = RiverReading(station=body.station, valid_utc=valid_utc, level_m=body.level_m, kind=body.kind.value,
                       lead_days=body.lead_days, issued_utc=issued, source_url=body.source_url, entered_by=body.entered_by)
    s.add(row)
    s.flush()
    ledger.write(s, ck.scope, "river_reading_added", actor=body.entered_by,
                 payload={"station": body.station, "level_m": body.level_m, "kind": body.kind.value})
    return {"id": row.id, "station": row.station, "valid_utc": row.valid_utc, "level_m": row.level_m, "kind": row.kind,
            "lead_days": row.lead_days, "issued_utc": row.issued_utc, "source_url": row.source_url,
            "entered_by": row.entered_by}


# ================================================================ wiring
_LOOP_STARTED = False


def _loop() -> None:
    while True:
        time.sleep(max(settings.TICK_S, 5))
        try:
            with session_scope() as s:
                engine.tick(s)
            with session_scope() as s, engine.LOCK:
                lifecycle.sweep(s)
        except Exception as exc:          # keep the loop alive; the next round may work
            print(f"[alerts] background round failed: {exc!r}")


def install(app: FastAPI) -> None:
    """Add the alert layer to the kit's FastAPI app: routes, the built phone app, and the background loop."""
    app.include_router(router)
    app.include_router(console)

    dist = ROOT / "web" / "app" / "dist"
    if (dist / "index.html").exists():
        app.mount("/app/assets", StaticFiles(directory=dist / "assets"), name="app-assets")

        @app.get("/app", include_in_schema=False)
        def app_root() -> RedirectResponse:
            return RedirectResponse("/app/")

        @app.get("/app/{path:path}", include_in_schema=False)
        def app_files(path: str) -> FileResponse:
            f = (dist / path).resolve()
            if path and f.is_file() and dist.resolve() in f.parents:
                return FileResponse(f)
            return FileResponse(dist / "index.html")      # client-side routes

    @app.get("/lab", include_in_schema=False)
    def lab() -> FileResponse:
        return FileResponse(ROOT / "web" / "index.html")

    @app.on_event("startup")
    def _start() -> None:
        global _LOOP_STARTED
        init_engine()
        if settings.TICK_S > 0 and not _LOOP_STARTED:
            _LOOP_STARTED = True
            threading.Thread(target=_loop, daemon=True, name="alerts-loop").start()
