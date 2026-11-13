"""Guided-demo routes: a private sandbox of the alert loop for each website visitor (no token needed)."""
from __future__ import annotations

import datetime as dt
from typing import Any, Iterator, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.alerts import sandbox, service
from src.alerts.db import get_session
from src.alerts.lifecycle import LifecycleError

router = APIRouter(prefix="/api/v1/sandbox", tags=["guided demo"])


def db() -> Iterator[Session]:
    yield from get_session()


class ClockBody(BaseModel):
    mode: Literal["live", "replay"] = "replay"
    as_of_utc: dt.datetime | None = None
    preset: Literal["start", "gap_rain"] | None = None


class VolunteerBody(BaseModel):
    volunteer: str = Field(default="Demo volunteer", min_length=1, max_length=60)


class RejectBody(VolunteerBody):
    reason: str = Field(min_length=3, max_length=300)


class JoinBody(BaseModel):
    device_id: str = Field(min_length=8, max_length=64)


def _guard(fn: Any) -> Any:
    try:
        return fn()
    except (sandbox.SandboxError, LifecycleError) as exc:
        raise HTTPException(409, str(exc))


@router.post("")
def create(s: Session = Depends(db)) -> dict[str, Any]:
    """Start a new guided demo: a replay clock at 26 Jul 2026 14:00 Dhaka and six demo phones at real places."""
    out = _guard(lambda: sandbox.create(s))
    return {**out, "snapshot": sandbox.snapshot(s, out["sandbox_id"])}


@router.get("/{sid}")
def get(sid: str, since_id: int = Query(0, ge=0), s: Session = Depends(db)) -> dict[str, Any]:
    return _guard(lambda: sandbox.snapshot(s, sid, since_id))


@router.put("/{sid}/clock")
def put_clock(sid: str, body: ClockBody, s: Session = Depends(db)) -> dict[str, Any]:
    as_of = body.as_of_utc
    if body.preset == "start":
        as_of = sandbox.START_UTC
    elif body.preset == "gap_rain":
        as_of = sandbox.GAP_RAIN_UTC
    _guard(lambda: sandbox.set_clock(s, sid, body.mode, as_of))
    return sandbox.snapshot(s, sid)


@router.post("/{sid}/next-event")
def next_event(sid: str, s: Session = Depends(db)) -> dict[str, Any]:
    _, label = _guard(lambda: sandbox.next_event(s, sid))
    return {"label": label, **sandbox.snapshot(s, sid)}


@router.post("/{sid}/tick")
def tick(sid: str, s: Session = Depends(db)) -> dict[str, Any]:
    out = _guard(lambda: sandbox.tick(s, sid))
    return {"tick": out, **sandbox.snapshot(s, sid)}


@router.post("/{sid}/events/{event_id}/approve")
def approve(sid: str, event_id: str, body: VolunteerBody, s: Session = Depends(db)) -> dict[str, Any]:
    ev = _guard(lambda: sandbox.approve(s, sid, event_id, body.volunteer))
    s.refresh(ev)
    return {"event": service.event_out(s, ev), **sandbox.snapshot(s, sid)}


@router.post("/{sid}/events/{event_id}/reject")
def reject(sid: str, event_id: str, body: RejectBody, s: Session = Depends(db)) -> dict[str, Any]:
    _guard(lambda: sandbox.reject(s, sid, event_id, body.volunteer, body.reason))
    return sandbox.snapshot(s, sid)


@router.post("/{sid}/callbacks/{recipient_id}/done")
def callback_done(sid: str, recipient_id: str, body: VolunteerBody, s: Session = Depends(db)) -> dict[str, Any]:
    _guard(lambda: sandbox.callback_done(s, sid, recipient_id, body.volunteer))
    return sandbox.snapshot(s, sid)


@router.post("/{sid}/simulate-replies")
def simulate_replies(sid: str, s: Session = Depends(db)) -> dict[str, Any]:
    """Demo households answer by keypad. Simulated and labelled: their channel is call_sim or sms_sim."""
    n = _guard(lambda: sandbox.simulate_household_replies(s, sid))
    return {"simulated_replies": n, **sandbox.snapshot(s, sid)}


@router.post("/{sid}/join")
def join(sid: str, body: JoinBody, s: Session = Depends(db)) -> dict[str, Any]:
    """A real phone joins this demo (from the QR code). It then gets this demo's alerts, by push if allowed."""
    p = _guard(lambda: sandbox.join(s, sid, body.device_id))
    return {"device_id": p.device_id, "sandbox_id": sid, "display_name": p.display_name}
