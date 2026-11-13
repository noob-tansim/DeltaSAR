"""Plain-text email through any SMTP account the team controls (SMTP_HOST, SMTP_USER, SMTP_PASSWORD, MAIL_FROM)."""
from __future__ import annotations

import smtplib
from email.message import EmailMessage

from src.alerts import settings


def send(to: str | None, subject: str, body: str) -> tuple[bool, str]:
    if not to:
        return False, "no email address"
    if not settings.SMTP_HOST or not settings.MAIL_FROM:
        return False, "SMTP not configured on the server"
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.MAIL_FROM, to, subject
    msg.set_content(body, charset="utf-8")
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as smtp:
            smtp.starttls()
            if settings.SMTP_USER:
                smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.send_message(msg)
        return True, "sent"
    except Exception as exc:
        return False, type(exc).__name__
