"""The clocks of the alert layer.

LIVE:   as_of = the real time.
REPLAY: as_of = a moment of the 2026 season chosen in the console. Rules then see only data that had been
        published by that moment. All inputs are the real archived ones; nothing is made up.

There is one shared clock (the volunteer console) and one clock per guided-demo sandbox ("sb-<id>"), so a judge
replaying July on the website never moves the clock the team's phones are using.

Nothing else in src/alerts/ asks the system for the time when deciding what a rule sees.
Approval and retry timers are different: they always run in real time (db.utcnow()).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy.orm import Session

from src.alerts.db import Person, Setting, utcnow
from src.alerts.types import ClockMode

SHARED = "shared"


@dataclass(frozen=True)
class Clock:
    mode: ClockMode
    as_of: dt.datetime      # timezone-aware UTC
    scope: str              # "live", "replay-<n>" or "sb-<id>": alerts of different scopes never mix

    @property
    def replay(self) -> bool:
        return self.mode == ClockMode.replay

    @property
    def sandbox(self) -> bool:
        return is_sandbox(self.scope)

    @property
    def people_scope(self) -> str:
        """Which people this clock's rules look at."""
        return self.scope if self.sandbox else SHARED


def is_sandbox(scope: str | None) -> bool:
    return bool(scope) and scope.startswith("sb-")  # type: ignore[union-attr]


def _get(s: Session, key: str, default: str) -> str:
    row = s.get(Setting, key)
    return row.value if row else default


def _set(s: Session, key: str, value: str) -> None:
    row = s.get(Setting, key)
    if row:
        row.value = value
    else:
        s.add(Setting(key=key, value=value))


def read(s: Session, scope: str | None = None) -> Clock:
    """The shared clock, or a sandbox clock when `scope` is "sb-<id>"."""
    if is_sandbox(scope):
        assert scope is not None
        mode = ClockMode(_get(s, f"{scope}:mode", "replay"))
        if mode == ClockMode.live:
            return Clock(mode, utcnow(), scope)
        raw = _get(s, f"{scope}:as_of", "")
        return Clock(mode, dt.datetime.fromisoformat(raw) if raw else utcnow(), scope)
    mode = ClockMode(_get(s, "clock_mode", "live"))
    if mode == ClockMode.live:
        return Clock(mode, utcnow(), "live")
    as_of = dt.datetime.fromisoformat(_get(s, "clock_as_of", utcnow().isoformat()))
    return Clock(mode, as_of, f"replay-{_get(s, 'replay_run', '1')}")


def for_person(s: Session, p: Person) -> Clock:
    return read(s, p.scope if is_sandbox(p.scope) else None)


def set_live(s: Session, scope: str | None = None) -> Clock:
    if is_sandbox(scope):
        _set(s, f"{scope}:mode", "live")
    else:
        _set(s, "clock_mode", "live")
    s.flush()
    return read(s, scope)


def set_replay(s: Session, as_of: dt.datetime, new_run: bool = False, scope: str | None = None) -> Clock:
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    iso = as_of.astimezone(dt.timezone.utc).isoformat()
    if is_sandbox(scope):
        _set(s, f"{scope}:mode", "replay")
        _set(s, f"{scope}:as_of", iso)
        s.flush()
        return read(s, scope)
    if new_run:
        _set(s, "replay_run", str(int(_get(s, "replay_run", "0")) + 1))
    elif s.get(Setting, "replay_run") is None:
        _set(s, "replay_run", "1")
    _set(s, "clock_mode", "replay")
    _set(s, "clock_as_of", iso)
    s.flush()
    return read(s)
