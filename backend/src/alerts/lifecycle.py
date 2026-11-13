"""What happens to a draft: approval, sending, acknowledgement, reply, retry, call-back, closing.

Timers here run in REAL time (db.utcnow), also during a replay: a volunteer and a phone act now.
Every state change writes exactly one ledger row.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.alerts import deliver, ledger, messages, settings
from src.alerts.db import AlertEvent, AlertRecipient, Delivery, Person, utcnow
from src.alerts.types import Channel, EventState, RecipientState, Reply

OPEN_RECIPIENT = (RecipientState.sent.value, RecipientState.acked.value)
FINAL_RECIPIENT = (RecipientState.replied_safe.value, RecipientState.replied_help.value,
                   RecipientState.no_reply_final.value, RecipientState.failed.value)


class LifecycleError(ValueError):
    pass


def seconds_left(ev: AlertEvent, now: dt.datetime | None = None) -> int | None:
    if ev.state not in (EventState.drafted.value, EventState.late.value):
        return None
    now = now or utcnow()
    return int(settings.APPROVAL_WINDOW_S - (now - ev.created_utc).total_seconds())


def _send(s: Session, ev: AlertEvent, rec: AlertRecipient, attempt: int) -> bool:
    person = s.get(Person, rec.person_id)
    assert person is not None
    full_bn, full_en = messages.full(rec.message_bn, rec.message_en)
    any_ok = False
    for name in person.channels or [Channel.in_app.value]:
        ch = Channel(name)
        ok, detail = deliver.send(s, ch, person, rec, full_bn, full_en)
        s.add(Delivery(alert_recipient_id=rec.id, channel=ch.value, attempt=attempt, result="ok" if ok else "failed",
                       detail=detail))
        ledger.write(s, ev.scope, "sent" if ok else "send_failed", event_id=ev.id, person_id=person.id,
                     payload={"channel": ch.value, "attempt": attempt, "detail": detail})
        any_ok = any_ok or ok
    now = utcnow()
    rec.last_send_utc = now
    if any_ok:
        if rec.sent_utc is None:
            rec.sent_utc = now
        if rec.state == RecipientState.queued.value:
            rec.state = RecipientState.sent.value
    elif rec.state == RecipientState.queued.value:
        rec.state = RecipientState.failed.value
    return any_ok


def approve(s: Session, event_id: str, volunteer: str) -> AlertEvent:
    ev = s.get(AlertEvent, event_id)
    if ev is None:
        raise LifecycleError("no such alert")
    if ev.state not in (EventState.drafted.value, EventState.late.value):
        raise LifecycleError(f"alert is already {ev.state}")
    ev.state, ev.approved_by, ev.approved_utc = EventState.approved.value, volunteer, utcnow()
    ledger.write(s, ev.scope, "approved", event_id=ev.id, actor=volunteer,
                 payload={"recipients": len(ev.recipients), "after_window": seconds_left_was_negative(ev)})
    for rec in ev.recipients:
        _send(s, ev, rec, attempt=1)
    ev.state = EventState.sent.value
    s.flush()
    return ev


def seconds_left_was_negative(ev: AlertEvent) -> bool:
    return (utcnow() - ev.created_utc).total_seconds() > settings.APPROVAL_WINDOW_S


def reject(s: Session, event_id: str, volunteer: str, reason: str) -> AlertEvent:
    ev = s.get(AlertEvent, event_id)
    if ev is None:
        raise LifecycleError("no such alert")
    if ev.state not in (EventState.drafted.value, EventState.late.value):
        raise LifecycleError(f"alert is already {ev.state}")
    ev.state, ev.rejected_reason, ev.approved_by = EventState.rejected.value, reason, volunteer
    ledger.write(s, ev.scope, "rejected", event_id=ev.id, actor=volunteer, payload={"reason": reason})
    s.flush()
    return ev


def _recipient(s: Session, recipient_id: str, device_id: str) -> tuple[AlertRecipient, AlertEvent, Person]:
    rec = s.get(AlertRecipient, recipient_id)
    if rec is None:
        raise LifecycleError("no such alert")
    person = s.get(Person, rec.person_id)
    if person is None or person.device_id != device_id:
        raise LifecycleError("this alert belongs to another device")
    ev = s.get(AlertEvent, rec.alert_event_id)
    assert ev is not None
    if ev.state not in (EventState.sent.value, EventState.closed.value):
        raise LifecycleError("this alert has not been sent")
    return rec, ev, person


def ack(s: Session, recipient_id: str, device_id: str) -> AlertRecipient:
    """The phone showed the alert. Idempotent: only the first acknowledgement is recorded."""
    rec, ev, person = _recipient(s, recipient_id, device_id)
    if rec.ack_utc is None:
        rec.ack_utc = utcnow()
        if rec.state == RecipientState.sent.value:
            rec.state = RecipientState.acked.value
        ledger.write(s, ev.scope, "acked", event_id=ev.id, person_id=person.id, actor="person")
        s.flush()
    return rec


def reply(s: Session, recipient_id: str, device_id: str, answer: Reply, via: Channel) -> AlertRecipient:
    """"I am safe" or "I need help". A person may change the answer; each change is one ledger row."""
    rec, ev, person = _recipient(s, recipient_id, device_id)
    if rec.reply == answer.value:
        return rec
    rec.reply, rec.reply_utc, rec.reply_via = answer.value, utcnow(), via.value
    rec.state = (RecipientState.replied_safe if answer == Reply.safe else RecipientState.replied_help).value
    if answer == Reply.help:
        rec.callback_done = False
    ledger.write(s, ev.scope, "reply_safe" if answer == Reply.safe else "reply_help", event_id=ev.id,
                 person_id=person.id, actor="person", payload={"via": via.value})
    _maybe_close(s, ev)
    s.flush()
    return rec


def callback_done(s: Session, recipient_id: str, volunteer: str) -> AlertRecipient:
    rec = s.get(AlertRecipient, recipient_id)
    if rec is None:
        raise LifecycleError("no such alert")
    if rec.reply != Reply.help.value:
        raise LifecycleError("this person did not ask for help")
    ev = s.get(AlertEvent, rec.alert_event_id)
    assert ev is not None
    if not rec.callback_done:
        rec.callback_done = True
        ledger.write(s, ev.scope, "callback_done", event_id=ev.id, person_id=rec.person_id, actor=volunteer)
        _maybe_close(s, ev)
        s.flush()
    return rec


def _maybe_close(s: Session, ev: AlertEvent) -> None:
    if ev.state != EventState.sent.value:
        return
    for r in ev.recipients:
        if r.state not in FINAL_RECIPIENT:
            return
        if r.state == RecipientState.replied_help.value and not r.callback_done:
            return
    ev.state = EventState.closed.value
    ledger.write(s, ev.scope, "closed", event_id=ev.id)


def sweep(s: Session, now: dt.datetime | None = None) -> dict[str, int]:
    """Real-time timers: mark late drafts, retry unanswered alerts (at most MAX_RETRIES), then give up."""
    now = now or utcnow()
    out = {"late": 0, "retried": 0, "no_reply_final": 0}
    for ev in s.scalars(select(AlertEvent).where(AlertEvent.state == EventState.drafted.value)):
        if (now - ev.created_utc).total_seconds() > settings.APPROVAL_WINDOW_S:
            ev.state = EventState.late.value          # stays in the queue; it never sends by itself
            ledger.write(s, ev.scope, "late", event_id=ev.id)
            out["late"] += 1
    for ev in s.scalars(select(AlertEvent).where(AlertEvent.state == EventState.sent.value)):
        for rec in ev.recipients:
            if rec.state not in OPEN_RECIPIENT or rec.reply is not None or rec.last_send_utc is None:
                continue
            if (now - rec.last_send_utc).total_seconds() < settings.RETRY_AFTER_S:
                continue
            if rec.retry_count < settings.MAX_RETRIES:
                rec.retry_count += 1
                ledger.write(s, ev.scope, "retry", event_id=ev.id, person_id=rec.person_id,
                             payload={"retry": rec.retry_count})
                _send(s, ev, rec, attempt=rec.retry_count + 1)
                rec.last_send_utc = now
                out["retried"] += 1
            else:
                rec.state = RecipientState.no_reply_final.value
                ledger.write(s, ev.scope, "no_reply_final", event_id=ev.id, person_id=rec.person_id)
                out["no_reply_final"] += 1
        _maybe_close(s, ev)
    s.flush()
    return out
