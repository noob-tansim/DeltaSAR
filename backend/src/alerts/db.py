"""Tables of the alert layer (SQLAlchemy 2). SQLite on a laptop, Postgres when DATABASE_URL says so."""
from __future__ import annotations

import datetime as dt
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import DateTime, TypeDecorator

from src.alerts.settings import database_url, normalize_url


def utcnow() -> dt.datetime:
    """Real wall-clock time. Rules never call this: they get `as_of` from clock.py."""
    return dt.datetime.now(dt.timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex


class UtcDateTime(TypeDecorator[dt.datetime]):
    """Stores naive UTC, returns timezone-aware UTC (SQLite drops the timezone otherwise)."""
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: dt.datetime | None, dialect: Any) -> dt.datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime given to the database; use timezone-aware UTC")
        return value.astimezone(dt.timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value: dt.datetime | None, dialect: Any) -> dt.datetime | None:
        return None if value is None else value.replace(tzinfo=dt.timezone.utc)


class Base(DeclarativeBase):
    pass


class Person(Base):
    __tablename__ = "person"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    device_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # "shared": people the volunteer console works with (LIVE and console REPLAY).
    # "sb-<id>": people inside one visitor's guided-demo sandbox; they never mix with anyone else's alerts.
    scope: Mapped[str] = mapped_column(String(20), default="shared", index=True)
    display_name: Mapped[str | None] = mapped_column(String(60))
    union_id: Mapped[str | None] = mapped_column(String(64))
    home_lat: Mapped[float] = mapped_column(Float)
    home_lon: Mapped[float] = mapped_column(Float)
    months: Mapped[list[int]] = mapped_column(JSON)
    rain_on: Mapped[bool] = mapped_column(Boolean, default=True)
    rain_mm: Mapped[int] = mapped_column(Integer, default=76)
    river_on: Mapped[bool] = mapped_column(Boolean, default=True)
    radar_on: Mapped[bool] = mapped_column(Boolean, default=True)
    radar_km: Mapped[float] = mapped_column(Float, default=1.0)
    channels: Mapped[list[str]] = mapped_column(JSON)
    email: Mapped[str | None] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(16))
    mode: Mapped[dict[str, Any]] = mapped_column(JSON)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True)
    consent_utc: Mapped[dt.datetime] = mapped_column(UtcDateTime)
    created_utc: Mapped[dt.datetime] = mapped_column(UtcDateTime, default=utcnow)
    subscriptions: Mapped[list["PushSub"]] = relationship(back_populates="person", cascade="all, delete-orphan")


class PushSub(Base):
    __tablename__ = "push_subscription"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    person_id: Mapped[str] = mapped_column(ForeignKey("person.id"), index=True)
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    p256dh: Mapped[str] = mapped_column(String(300))
    auth: Mapped[str] = mapped_column(String(120))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    created_utc: Mapped[dt.datetime] = mapped_column(UtcDateTime, default=utcnow)
    person: Mapped[Person] = relationship(back_populates="subscriptions")


class RiverReading(Base):
    __tablename__ = "river_reading"
    __table_args__ = (UniqueConstraint("station", "valid_utc", "kind", "issued_utc", name="uq_river_reading"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    station: Mapped[str] = mapped_column(String(40), index=True)
    valid_utc: Mapped[dt.datetime] = mapped_column(UtcDateTime)
    level_m: Mapped[float] = mapped_column(Float)
    kind: Mapped[str] = mapped_column(String(10))
    lead_days: Mapped[int] = mapped_column(Integer, default=0)
    issued_utc: Mapped[dt.datetime] = mapped_column(UtcDateTime, index=True)
    source_url: Mapped[str] = mapped_column(Text)
    entered_by: Mapped[str] = mapped_column(String(60))
    created_utc: Mapped[dt.datetime] = mapped_column(UtcDateTime, default=utcnow)


class RainDaily(Base):
    """One 24-hour rain total for the covered area. `visible_utc` is when the value could first be known."""
    __tablename__ = "rain_daily"
    date: Mapped[str] = mapped_column(String(10), primary_key=True)      # YYYY-MM-DD (UTC day of the product)
    mm: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(Text)
    visible_utc: Mapped[dt.datetime] = mapped_column(UtcDateTime, index=True)


class AlertEvent(Base):
    """One row per rule and event inside one scope ("live" or "replay-<n>"). The volunteer approves this row."""
    __tablename__ = "alert_event"
    __table_args__ = (UniqueConstraint("scope", "rule", "event_key", name="uq_event"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    scope: Mapped[str] = mapped_column(String(20), index=True)
    rule: Mapped[str] = mapped_column(String(10))
    event_key: Mapped[str] = mapped_column(String(80))
    as_of_utc: Mapped[dt.datetime] = mapped_column(UtcDateTime)
    replay: Mapped[bool] = mapped_column(Boolean, default=False)
    state: Mapped[str] = mapped_column(String(12), index=True, default="drafted")
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON)
    input_checks: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    message_bn: Mapped[str] = mapped_column(Text)
    message_en: Mapped[str] = mapped_column(Text)
    approved_by: Mapped[str | None] = mapped_column(String(60))
    approved_utc: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)
    rejected_reason: Mapped[str | None] = mapped_column(String(300))
    created_utc: Mapped[dt.datetime] = mapped_column(UtcDateTime, default=utcnow)
    recipients: Mapped[list["AlertRecipient"]] = relationship(back_populates="event", cascade="all, delete-orphan")


class AlertRecipient(Base):
    __tablename__ = "alert_recipient"
    __table_args__ = (UniqueConstraint("alert_event_id", "person_id", name="uq_recipient"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    alert_event_id: Mapped[str] = mapped_column(ForeignKey("alert_event.id"), index=True)
    person_id: Mapped[str] = mapped_column(ForeignKey("person.id"), index=True)
    values: Mapped[dict[str, Any]] = mapped_column(JSON)
    confidence: Mapped[str] = mapped_column(String(10))
    message_bn: Mapped[str] = mapped_column(Text)
    message_en: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(16), default="queued")
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    sent_utc: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)
    last_send_utc: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)
    ack_utc: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)
    reply: Mapped[str | None] = mapped_column(String(6))
    reply_utc: Mapped[dt.datetime | None] = mapped_column(UtcDateTime)
    reply_via: Mapped[str | None] = mapped_column(String(10))
    callback_done: Mapped[bool] = mapped_column(Boolean, default=False)
    created_utc: Mapped[dt.datetime] = mapped_column(UtcDateTime, default=utcnow)
    event: Mapped[AlertEvent] = relationship(back_populates="recipients")
    person: Mapped[Person] = relationship()


class Delivery(Base):
    __tablename__ = "delivery"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    alert_recipient_id: Mapped[str] = mapped_column(ForeignKey("alert_recipient.id"), index=True)
    channel: Mapped[str] = mapped_column(String(10))
    attempt: Mapped[int] = mapped_column(Integer)
    result: Mapped[str] = mapped_column(String(8))          # ok | failed
    detail: Mapped[str] = mapped_column(Text, default="")
    utc: Mapped[dt.datetime] = mapped_column(UtcDateTime, default=utcnow)


class Ledger(Base):
    """Append only. Impact numbers are counted from here and nowhere else."""
    __tablename__ = "ledger"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    utc: Mapped[dt.datetime] = mapped_column(UtcDateTime, default=utcnow, index=True)
    scope: Mapped[str] = mapped_column(String(20), index=True)
    kind: Mapped[str] = mapped_column(String(24), index=True)
    alert_event_id: Mapped[str | None] = mapped_column(String(32), index=True)
    person_id: Mapped[str | None] = mapped_column(String(32))
    actor: Mapped[str] = mapped_column(String(60), default="system")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Setting(Base):
    __tablename__ = "setting"
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


_engine: Engine | None = None
_Session: sessionmaker[Session] | None = None


def init_engine(url: str | None = None) -> Engine:
    """Create the engine and the tables. Called once at start-up (and by tests with an in-memory URL)."""
    global _engine, _Session
    if _engine is not None:                    # re-initialising (tests): close the old pool's connections first
        _engine.dispose()
    url = normalize_url(url) if url else database_url()
    kwargs: dict[str, Any] = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url:
            kwargs["poolclass"] = StaticPool
    else:                                      # hosted Postgres: drop dead connections, stay small on free tiers
        kwargs.update(pool_pre_ping=True, pool_size=3, max_overflow=2, pool_recycle=300)   # Supabase free pooler: ~15 connections in all
    _engine = create_engine(url, **kwargs)
    _Session = sessionmaker(_engine, expire_on_commit=False)
    Base.metadata.create_all(_engine)
    return _engine


@contextmanager
def session_scope() -> Iterator[Session]:
    if _Session is None:
        init_engine()
    assert _Session is not None
    s = _Session()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    with session_scope() as s:
        yield s
