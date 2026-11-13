"""Typed contract of the alert layer. Every input has a range; a value outside it is rejected (HTTP 422).

The front end gets these types through FastAPI's OpenAPI document (web/app: `npm run gen:api`).
"""
from __future__ import annotations

import datetime as dt
import re
from enum import Enum
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

from src.alerts.settings import AOI_BBOX

# ---------------------------------------------------------------- ranges (single source of truth)
DB_MIN, DB_MAX = -35.0, 5.0
RAIN_DATA_MIN_MM, RAIN_DATA_MAX_MM = 0.0, 500.0
RAIN_USER_MIN_MM, RAIN_USER_MAX_MM, RAIN_USER_STEP = 10, 300, 5
RAIN_USER_PRESETS = (76, 152)          # 3 in and 6 in
RIVER_MIN_M, RIVER_MAX_M = 5.0, 25.0
RADAR_KM_MIN, RADAR_KM_MAX, RADAR_KM_DEFAULT = 0.2, 5.0, 1.0
LEAD_DAYS_MAX = 5
DHAKA = dt.timezone(dt.timedelta(hours=6), "Asia/Dhaka")   # Bangladesh has no daylight saving time


def _aware_utc(v: dt.datetime) -> dt.datetime:
    if v.tzinfo is None:
        raise ValueError("datetime must carry a timezone")
    return v.astimezone(dt.timezone.utc)


UtcDatetime = Annotated[dt.datetime, AfterValidator(_aware_utc)]


def in_aoi(lat: float, lon: float) -> bool:
    w, s, e, n = AOI_BBOX
    return w <= lon <= e and s <= lat <= n


# ---------------------------------------------------------------- enums
class Reply(str, Enum):
    safe = "safe"
    help = "help"


class Channel(str, Enum):
    in_app = "in_app"        # always on: the open app polls its status
    push = "push"
    email = "email"
    call_sim = "call_sim"    # simulated, always labelled "demo"
    sms_sim = "sms_sim"      # simulated, always labelled "demo"


class Confidence(str, Enum):
    sure = "sure"
    less_sure = "less_sure"
    unknown = "unknown"


class Status(str, Enum):
    calm = "calm"
    watch = "watch"
    alert = "alert"
    no_data = "no_data"


class RuleName(str, Enum):
    radar = "radar"
    river = "river"
    rain = "rain"


class ClockMode(str, Enum):
    live = "live"
    replay = "replay"


class EventState(str, Enum):
    drafted = "drafted"
    late = "late"            # not approved inside the window; stays in the queue, never sends by itself
    rejected = "rejected"
    approved = "approved"
    sent = "sent"
    closed = "closed"


class RecipientState(str, Enum):
    queued = "queued"
    sent = "sent"
    acked = "acked"
    replied_safe = "replied_safe"
    replied_help = "replied_help"
    no_reply_final = "no_reply_final"
    failed = "failed"


class ReadingKind(str, Enum):
    observed = "observed"
    forecast = "forecast"


# ---------------------------------------------------------------- people
class PersonMode(BaseModel):
    listen: bool = False
    pictures: bool = False
    large_text: bool = False
    vibrate_light: bool = False
    sign: bool = False


_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE = re.compile(r"^\+?[0-9]{8,15}$")


class PersonIn(BaseModel):
    """Settings a person chooses on the Join and My-alerts screens."""
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, max_length=60)
    union_id: str | None = Field(default=None, max_length=64)
    home_lat: float = Field(ge=-90, le=90)
    home_lon: float = Field(ge=-180, le=180)
    months: list[int] = Field(default_factory=lambda: [6, 7, 8, 9, 10], min_length=1, max_length=12)
    rain_on: bool = True
    rain_mm: int = Field(default=76, ge=RAIN_USER_MIN_MM, le=RAIN_USER_MAX_MM)
    river_on: bool = True
    radar_on: bool = True
    radar_km: float = Field(default=RADAR_KM_DEFAULT, ge=RADAR_KM_MIN, le=RADAR_KM_MAX)
    channels: list[Channel] = Field(default_factory=lambda: [Channel.in_app])
    email: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=16)
    mode: PersonMode = Field(default_factory=PersonMode)
    consent: bool = Field(description="The person agreed that the contact details are used for alerts only.")

    @field_validator("months")
    @classmethod
    def _months(cls, v: list[int]) -> list[int]:
        if any(m < 1 or m > 12 for m in v):
            raise ValueError("months must be 1 to 12")
        return sorted(set(v))

    @field_validator("rain_mm")
    @classmethod
    def _rain(cls, v: int) -> int:
        if v % RAIN_USER_STEP and v not in RAIN_USER_PRESETS:
            raise ValueError("rain level must be a multiple of 5 mm, or 76 (3 in) or 152 (6 in)")
        return v

    @field_validator("email")
    @classmethod
    def _email(cls, v: str | None) -> str | None:
        if v in (None, ""):
            return None
        if not _EMAIL.match(v):
            raise ValueError("not an email address")
        return v

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str | None) -> str | None:
        if v in (None, ""):
            return None
        v = v.replace(" ", "").replace("-", "")
        if not _PHONE.match(v):
            raise ValueError("phone must be 8 to 15 digits")
        return v

    @field_validator("channels")
    @classmethod
    def _channels(cls, v: list[Channel]) -> list[Channel]:
        out = list(dict.fromkeys(v))
        if Channel.in_app not in out:
            out.insert(0, Channel.in_app)
        return out

    @model_validator(mode="after")
    def _checks(self) -> "PersonIn":
        if not in_aoi(self.home_lat, self.home_lon):
            w, s, e, n = AOI_BBOX
            raise ValueError(f"home is outside the covered area (lon {w} to {e}, lat {s} to {n})")
        if not self.consent:
            raise ValueError("consent is required")
        if Channel.email in self.channels and not self.email:
            raise ValueError("email channel chosen but no email address given")
        return self


class PersonOut(BaseModel):
    device_id: str
    display_name: str | None
    union_id: str | None
    home_lat: float
    home_lon: float
    months: list[int]
    rain_on: bool
    rain_mm: int
    river_on: bool
    radar_on: bool
    radar_km: float
    channels: list[Channel]
    email: str | None
    phone: str | None
    mode: PersonMode
    is_demo: bool
    has_push: bool
    created_utc: dt.datetime


class UnionOut(BaseModel):
    union_id: str
    name_en: str
    name_bn: str | None = None
    upazila_en: str | None = None
    upazila_bn: str | None = None
    lat: float
    lon: float


class PushSubscriptionKeys(BaseModel):
    p256dh: str = Field(min_length=10, max_length=300)
    auth: str = Field(min_length=4, max_length=120)


class PushSubscription(BaseModel):
    endpoint: str = Field(min_length=10, max_length=1000, pattern=r"^https://")
    keys: PushSubscriptionKeys


class PushSubscribeIn(BaseModel):
    device_id: str = Field(min_length=8, max_length=64)
    subscription: PushSubscription
    user_agent: str | None = Field(default=None, max_length=300)


# ---------------------------------------------------------------- status (home screen)
class RadarStatus(BaseModel):
    track: str
    pass_utc: dt.datetime
    pass_local: str
    published_utc: dt.datetime | None
    age_days: float
    stale: bool
    processing_level: str
    new_water_distance_m: int | None
    walk_minutes: int | None
    confidence: Confidence
    grew_since_previous_pass: bool | None
    next_expected_local_date: str | None
    overlay_url: str | None
    overlay_bounds: list[float] | None


class RiverStatus(BaseModel):
    station: str
    level_m: float | None
    danger_level_m: float
    line_m: float
    kind: ReadingKind | None
    valid_local: str | None
    age_hours: float | None
    stale: bool
    source_url: str | None


class RainStatus(BaseModel):
    date: str | None
    last_24h_mm: float | None
    limit_mm: int
    source: str | None
    stale: bool


class AlertOut(BaseModel):
    """One alert as one person sees it."""
    recipient_id: str
    event_id: str
    rule: RuleName
    event_state: EventState
    state: RecipientState
    confidence: Confidence
    message_bn: str
    message_en: str
    values: dict[str, Any]
    replay: bool
    as_of_utc: dt.datetime
    created_utc: dt.datetime
    approved_by: str | None
    approved_utc: dt.datetime | None
    sent_utc: dt.datetime | None
    ack_utc: dt.datetime | None
    reply: Reply | None
    reply_utc: dt.datetime | None
    reply_via: str | None
    channels: list[Channel]
    not_official_bn: str
    not_official_en: str


class StatusOut(BaseModel):
    as_of_utc: dt.datetime
    replay: bool
    status: Status
    reasons: list[str]
    covered: bool
    in_radar_gap: bool
    union: UnionOut | None
    radar: RadarStatus | None
    river: RiverStatus | None
    rain: RainStatus | None
    active_alert: AlertOut | None
    sources: list[str]
    not_official: bool = True


class EvidenceRow(BaseModel):
    key: str                 # what | where | when | how_sure
    label_bn: str
    label_en: str
    value_bn: str
    value_en: str


class OverlayRef(BaseModel):
    id: str
    label: str
    url: str
    bounds: list[float]      # west, south, east, north


class EvidenceOut(BaseModel):
    recipient_id: str
    rule: RuleName
    rows: list[EvidenceRow]
    receipt: dict[str, Any]
    overlays: list[OverlayRef]
    not_official_bn: str
    not_official_en: str


class RainDay(BaseModel):
    date: str
    mm: float


class RainOut(BaseModel):
    as_of_utc: dt.datetime
    replay: bool
    days: list[RainDay]
    limit_mm: int
    source: str | None
    note: str


class AckIn(BaseModel):
    device_id: str = Field(min_length=8, max_length=64)


class ReplyIn(BaseModel):
    device_id: str = Field(min_length=8, max_length=64)
    reply: Reply
    via: Channel = Channel.in_app


# ---------------------------------------------------------------- console
class InputCheck(BaseModel):
    name: str
    value: str
    allowed: str
    ok: bool


class RecipientOut(BaseModel):
    recipient_id: str
    person_id: str
    display_name: str | None
    union_name: str | None
    confidence: Confidence
    values: dict[str, Any]
    state: RecipientState
    retry_count: int
    reply: Reply | None
    reply_utc: dt.datetime | None
    reply_via: str | None
    callback_done: bool
    channels: list[Channel]


class EventOut(BaseModel):
    event_id: str
    rule: RuleName
    event_key: str
    scope: str
    state: EventState
    replay: bool
    as_of_utc: dt.datetime
    created_utc: dt.datetime
    seconds_left: int | None          # until the approval window closes; None once decided
    message_bn: str
    message_en: str
    approved_by: str | None
    approved_utc: dt.datetime | None
    rejected_reason: str | None
    evidence: dict[str, Any]
    input_checks: list[InputCheck]
    recipients: list[RecipientOut]


class ApproveIn(BaseModel):
    volunteer: str = Field(min_length=2, max_length=60)


class RejectIn(BaseModel):
    volunteer: str = Field(min_length=2, max_length=60)
    reason: str = Field(min_length=3, max_length=300)


class CallbackIn(BaseModel):
    volunteer: str = Field(min_length=2, max_length=60)


class LedgerRow(BaseModel):
    id: int
    utc: dt.datetime
    scope: str
    kind: str
    alert_event_id: str | None
    person_id: str | None
    actor: str
    payload: dict[str, Any]


class ImpactOut(BaseModel):
    scope: str
    participants_note: str
    drafts_created: int
    approved: int
    rejected: int
    late: int
    alerts_sent: int
    sends_ok_by_channel: dict[str, int]
    sends_failed_by_channel: dict[str, int]
    acknowledged: int
    replies_safe: int
    replies_help: int
    no_reply_final: int
    callbacks_done: int
    median_minutes_input_to_approval: float | None
    median_minutes_approval_to_first_ack: float | None


class RuleReport(BaseModel):
    rule: RuleName
    people_checked: int
    fired: int
    reasons: dict[str, int]          # reason text -> number of people


class InputsOut(BaseModel):
    as_of_utc: dt.datetime
    replay: bool
    radar: dict[str, Any] | None
    river: list[dict[str, Any]]
    rain: dict[str, Any] | None
    checks: list[InputCheck]
    last_tick_utc: dt.datetime | None
    rules: list[RuleReport]


class RiverReadingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    station: str = Field(min_length=2, max_length=40)
    valid_local: dt.datetime = Field(description="Time the level applies to, Asia/Dhaka wall time (naive) or aware.")
    level_m: float = Field(ge=RIVER_MIN_M, le=RIVER_MAX_M)
    kind: ReadingKind = ReadingKind.observed
    lead_days: int = Field(default=0, ge=0, le=LEAD_DAYS_MAX)
    issued_utc: UtcDatetime | None = None
    source_url: str = Field(min_length=8, max_length=400)
    entered_by: str = Field(min_length=2, max_length=60)

    @model_validator(mode="after")
    def _lead(self) -> "RiverReadingIn":
        if self.kind == ReadingKind.observed and self.lead_days != 0:
            raise ValueError("an observed reading has lead_days = 0")
        return self


class RiverReadingOut(BaseModel):
    id: str
    station: str
    valid_utc: dt.datetime
    level_m: float
    kind: ReadingKind
    lead_days: int
    issued_utc: dt.datetime
    source_url: str
    entered_by: str


class ClockOut(BaseModel):
    mode: ClockMode
    as_of_utc: dt.datetime
    real_utc: dt.datetime
    scope: str
    demo_timing: bool
    approval_window_s: int
    retry_after_s: int
    max_retries: int
    next_event_utc: dt.datetime | None
    next_event_label: str | None


class ClockIn(BaseModel):
    mode: ClockMode
    as_of_utc: UtcDatetime | None = None
    new_run: bool = Field(default=False, description="Start a fresh replay run: earlier replay alerts stay in the ledger "
                                                     "but no longer block new drafts for the same event.")

    @model_validator(mode="after")
    def _need_time(self) -> "ClockIn":
        if self.mode == ClockMode.replay and self.as_of_utc is None:
            raise ValueError("replay needs as_of_utc")
        return self


class TickOut(BaseModel):
    as_of_utc: dt.datetime
    replay: bool
    drafts_created: int
    recipients_added: int
    rules: list[RuleReport]
