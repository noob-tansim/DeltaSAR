"""Settings for the alert layer. Everything comes from environment variables (or ROOT/.env, read by src.config)."""
from __future__ import annotations

import os

from src.config import AOIS, OUTPUTS, ROOT  # importing config also loads ROOT/.env

AOI = os.environ.get("DELTASAR_AOI", "kazipur")
_bbox = tuple(float(v) for v in AOIS[AOI]["bbox"])  # type: ignore[attr-defined]
AOI_BBOX: tuple[float, float, float, float] = (_bbox[0], _bbox[1], _bbox[2], _bbox[3])  # west, south, east, north
DATA = ROOT / "data"
SANDBOX_TTL_H = float(os.environ.get("SANDBOX_TTL_H", 12))      # guided-demo sandboxes are removed after this
SANDBOX_MAX_PER_HOUR = int(os.environ.get("SANDBOX_MAX_PER_HOUR", 60))
AOI_OUT = OUTPUTS / AOI
RADAR_RULE_DIR = AOI_OUT / "radar_rule"


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def _float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


def database_url() -> str:
    return normalize_url(os.environ.get("DATABASE_URL") or f"sqlite:///{(ROOT / 'deltasar.db').as_posix()}")


def normalize_url(url: str) -> str:
    if url.startswith("postgres://"):          # some hosts still hand out the old scheme
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):        # use the psycopg 3 driver (Supabase, Render, any Postgres)
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


CONSOLE_TOKEN = os.environ.get("CONSOLE_TOKEN", "demo-token")

# Real-time timers. The defaults are the team's rule (15 min approval, 20 min retry, two retries).
# For a live demo set smaller values; the console then shows "demo timing".
APPROVAL_WINDOW_S = _int("APPROVAL_WINDOW_S", 900)
RETRY_AFTER_S = _int("RETRY_AFTER_S", 1200)
MAX_RETRIES = _int("MAX_RETRIES", 2)
TICK_S = _int("TICK_S", 30)                    # 0 = no background loop (tests)
DEMO_TIMING = APPROVAL_WINDOW_S != 900 or RETRY_AFTER_S != 1200

# Rule limits
RIVER_MAX_AGE_H = _float("RIVER_MAX_AGE_H", 24.0)
RIVER_LINE_BELOW_DL_M = 0.30
RIVER_WATCH_BELOW_DL_M = 0.60
RIVER_MAX_LEAD_DAYS = 3
RADAR_MAX_UNKNOWN_PCT = 5.0
RADAR_MAX_AGE_D = _float("RADAR_MAX_AGE_D", 14.0)   # a radar alert is never drafted from an older picture
RADAR_STALE_D = 24.0                                # home screen says "no new data" beyond this
RADAR_MIN_PATCH_HA = _float("RADAR_MIN_PATCH_HA", 1.0)
RAIN_MAX_AGE_D = 3.0
WALK_M_PER_MIN = 80.0
ALERT_ACTIVE_H = 72.0

# Delivery
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "mailto:team@example.org")
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = _int("SMTP_PORT", 587)
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
MAIL_FROM = os.environ.get("MAIL_FROM", "")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "")   # the web app, e.g. https://deltasar.vercel.app (links in emails)
WEB_DATA_BASE = os.environ.get("WEB_DATA_BASE", "/data")      # where the web app serves its static map pictures

RULE_VERSION = "1.0"
NOT_OFFICIAL_EN = "Not an official warning. Official forecasts: FFWC, BMD, call 1090."
NOT_OFFICIAL_BN = "এটি সরকারি সতর্কবার্তা নয়। সরকারি পূর্বাভাস শুনতে ১০৯০ নম্বরে ফোন করুন।"
