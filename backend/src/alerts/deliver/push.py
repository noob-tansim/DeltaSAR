"""Web Push (VAPID). Needs VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY (make them with jobs/make_vapid_keys.py)."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from src.alerts import settings
from src.alerts.db import Person, PushSub


def send(s: Session, person: Person, payload: dict[str, Any]) -> tuple[bool, str]:
    if not settings.VAPID_PRIVATE_KEY or not settings.VAPID_PUBLIC_KEY:
        return False, "VAPID keys not set on the server"
    subs = list(person.subscriptions)
    if not subs:
        return False, "this person has no push subscription"
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        return False, "pywebpush is not installed"
    ok, notes = 0, []
    for sub in subs:
        try:
            webpush(subscription_info={"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
                    data=json.dumps(payload, ensure_ascii=False), vapid_private_key=settings.VAPID_PRIVATE_KEY,
                    vapid_claims={"sub": settings.VAPID_SUBJECT}, ttl=3600, timeout=15)
            ok += 1
        except WebPushException as exc:
            code = getattr(getattr(exc, "response", None), "status_code", None)
            notes.append(f"HTTP {code}" if code else type(exc).__name__)
            if code in (404, 410):            # the browser dropped this subscription
                s.delete(s.get(PushSub, sub.id))
        except Exception as exc:              # network error and the like
            notes.append(type(exc).__name__)
    if ok:
        return True, f"{ok} of {len(subs)} device(s)" + (f"; failed: {', '.join(notes)}" if notes else "")
    return False, "; ".join(notes) or "push failed"
