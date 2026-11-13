"""Append-only ledger. Every state change writes exactly one row; impact numbers are counts of these rows."""
from __future__ import annotations

import datetime as dt
import statistics
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.alerts.db import Ledger

KINDS = {
    "input_seen", "rule_evaluated", "draft_created", "recipient_added", "approved", "rejected", "late",
    "sent", "send_failed", "acked", "reply_safe", "reply_help", "retry", "no_reply_final",
    "callback_done", "closed", "clock_set", "river_reading_added", "sandbox_created", "person_joined",
}


def write(s: Session, scope: str, kind: str, *, event_id: str | None = None, person_id: str | None = None,
          actor: str = "system", payload: dict[str, Any] | None = None) -> Ledger:
    if kind not in KINDS:
        raise ValueError(f"unknown ledger kind: {kind}")
    row = Ledger(scope=scope, kind=kind, alert_event_id=event_id, person_id=person_id, actor=actor,
                 payload=payload or {})
    s.add(row)
    s.flush()
    return row


def _count(s: Session, scope: str, kind: str) -> int:
    return int(s.scalar(select(func.count()).select_from(Ledger).where(Ledger.scope == scope, Ledger.kind == kind)) or 0)


def _by_channel(s: Session, scope: str, kind: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in s.scalars(select(Ledger).where(Ledger.scope == scope, Ledger.kind == kind)):
        ch = str(row.payload.get("channel", "?"))
        out[ch] = out.get(ch, 0) + 1
    return out


def _first_time(s: Session, scope: str, kind: str) -> dict[str, dt.datetime]:
    out: dict[str, dt.datetime] = {}
    for row in s.scalars(select(Ledger).where(Ledger.scope == scope, Ledger.kind == kind).order_by(Ledger.id)):
        if row.alert_event_id and row.alert_event_id not in out:
            out[row.alert_event_id] = row.utc
    return out


def impact(s: Session, scope: str) -> dict[str, Any]:
    """All figures come from ledger rows of one scope."""
    drafted, approved, acked = (_first_time(s, scope, k) for k in ("draft_created", "approved", "acked"))
    to_approval = [(approved[e] - drafted[e]).total_seconds() / 60 for e in approved if e in drafted]
    to_ack = [(acked[e] - approved[e]).total_seconds() / 60 for e in acked if e in approved]
    people_sent = {(r.alert_event_id, r.person_id) for r in
                   s.scalars(select(Ledger).where(Ledger.scope == scope, Ledger.kind == "sent"))}
    return {
        "scope": scope,
        "participants_note": "Demo participants only (team members and consenting testers).",
        "drafts_created": _count(s, scope, "draft_created"),
        "approved": _count(s, scope, "approved"),
        "rejected": _count(s, scope, "rejected"),
        "late": _count(s, scope, "late"),
        "alerts_sent": len(people_sent),
        "sends_ok_by_channel": _by_channel(s, scope, "sent"),
        "sends_failed_by_channel": _by_channel(s, scope, "send_failed"),
        "acknowledged": _count(s, scope, "acked"),
        "replies_safe": _count(s, scope, "reply_safe"),
        "replies_help": _count(s, scope, "reply_help"),
        "no_reply_final": _count(s, scope, "no_reply_final"),
        "callbacks_done": _count(s, scope, "callback_done"),
        "median_minutes_input_to_approval": round(statistics.median(to_approval), 1) if to_approval else None,
        "median_minutes_approval_to_first_ack": round(statistics.median(to_ack), 1) if to_ack else None,
    }
