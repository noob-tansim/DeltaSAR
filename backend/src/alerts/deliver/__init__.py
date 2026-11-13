"""Delivery adapters. Each returns (ok, detail). Simulated channels say so in the detail text."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from src.alerts import settings
from src.alerts.db import AlertRecipient, Person
from src.alerts.deliver import email as email_ch
from src.alerts.deliver import push as push_ch
from src.alerts.types import Channel


def alert_link(recipient_id: str) -> str:
    return f"{settings.PUBLIC_BASE_URL.rstrip('/')}/app/alert/{recipient_id}"


def send(s: Session, channel: Channel, person: Person, rec: AlertRecipient, full_bn: str, full_en: str) -> tuple[bool, str]:
    if channel == Channel.in_app:
        return True, "shown in the app when it next asks for its status"
    if channel == Channel.push:
        payload: dict[str, Any] = {"title": "বন্যা সাথী", "body": rec.message_bn, "recipient_id": rec.id,
                                   "url": f"/app/alert/{rec.id}", "vibrate": [300, 150, 300, 150, 600]}
        return push_ch.send(s, person, payload)
    if channel == Channel.email:
        return email_ch.send(person.email, "বন্যা সাথী: সতর্কবার্তা / Bonna Sathi alert",
                             f"{full_bn}\n\n{full_en}\n\n{alert_link(rec.id)}\n")
    if channel == Channel.call_sim:
        return True, "DEMO: simulated phone call (played inside the app)"
    if channel == Channel.sms_sim:
        return True, "DEMO: simulated SMS (shown in the console)"
    return False, f"unknown channel {channel}"
