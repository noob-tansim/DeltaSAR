"""Replay clock, engine (drafting and de-duplication), life cycle (approval, replies, retries) and the ledger."""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import func, select

from src.alerts import clock, engine, inputs, ledger, lifecycle, settings
from src.alerts.db import AlertEvent, AlertRecipient, Delivery, Ledger, RainDaily, RiverReading, utcnow
from src.alerts.types import Channel, EventState, RecipientState, Reply
from tests.conftest import add_person, utc

NEAR, FAR, EDGE = (24.69, 89.75), (24.60, 89.80), (24.50, 89.70)


def kinds(s, kind: str) -> int:
    return int(s.scalar(select(func.count()).select_from(Ledger).where(Ledger.kind == kind)) or 0)


def setup_people(s, table):
    table[NEAR] = (200.0, 150.0, 100.0)       # sure
    table[EDGE] = (1600.0, 900.0, 300.0)      # fires at T, not at T - 1 dB: less sure
    table[FAR] = (4000.0, 3000.0, 2500.0)     # beyond 1 km
    return (add_person(s, "device-near", *NEAR), add_person(s, "device-edge", *EDGE), add_person(s, "device-far", *FAR))


# ---------------------------------------------------------------- replay clock
def test_replay_sees_only_published_passes(fake_radar):
    # 24 Jul was acquired on the 24th but published on 27 Jul 07:21 UTC
    assert inputs.latest_pass(utc(2026, 7, 27, 7, 0)).date == "20260712"
    assert inputs.latest_pass(utc(2026, 7, 27, 7, 22)).date == "20260724"
    assert inputs.latest_pass(utc(2026, 7, 1)) is None            # even the baseline was not published yet


def test_radar_gap_is_known():
    assert inputs.in_radar_gap(utc(2026, 8, 5))
    assert not inputs.in_radar_gap(utc(2026, 7, 27, 8, 0))
    assert not inputs.in_radar_gap(utc(2026, 8, 11))


def test_clock_modes_and_scopes(session):
    assert clock.read(session).scope == "live"
    c1 = clock.set_replay(session, utc(2026, 7, 27, 8, 0), new_run=True)
    assert c1.replay and c1.as_of == utc(2026, 7, 27, 8, 0) and c1.scope == "replay-1"
    assert clock.set_replay(session, utc(2026, 8, 1)).scope == "replay-1"
    assert clock.set_replay(session, utc(2026, 7, 27, 8, 0), new_run=True).scope == "replay-2"
    assert clock.set_live(session).scope == "live"
    with pytest.raises(ValueError):
        clock.set_replay(session, dt.datetime(2026, 7, 27, 8, 0))   # naive time


def test_rules_and_inputs_never_read_the_system_clock():
    """What a rule sees depends only on `as_of`. Only clock.py and the real-time timers may ask for the time."""
    import pathlib
    import re
    root = pathlib.Path(__file__).resolve().parents[1] / "src" / "alerts"
    for name in ("rules.py", "inputs.py", "messages.py"):
        text = (root / name).read_text(encoding="utf-8")
        assert not re.search(r"utcnow\(|datetime\.now\(|date\.today\(|time\.time\(", text), name


# ---------------------------------------------------------------- engine
def test_tick_drafts_one_event_with_the_right_people(session, fake_radar):
    near, edge, far = setup_people(session, fake_radar)
    clock.set_replay(session, utc(2026, 7, 27, 8, 0), new_run=True)
    out = engine.tick(session)
    assert out["drafts_created"] == 1
    ev = session.scalars(select(AlertEvent)).one()
    assert (ev.rule, ev.event_key, ev.state, ev.replay) == ("radar", "069A_20260724", "drafted", True)
    conf = {r.person_id: r.confidence for r in ev.recipients}
    assert conf == {near.id: "sure", edge.id: "less_sure"}
    assert ev.evidence["input"]["granule_id"] == "G_069A_20260724"
    assert ev.evidence["aoi_result"]["new_water_km2_range"] == [300.0, 560.0]
    assert all(c["ok"] for c in ev.input_checks)
    radar_report = next(r for r in out["rules"] if r["rule"] == "radar")
    assert radar_report["fired"] == 2 and radar_report["reasons"]["nearest new water is beyond the person's distance"] == 1


def test_two_ticks_make_one_draft_not_two(session, fake_radar):
    setup_people(session, fake_radar)
    clock.set_replay(session, utc(2026, 7, 27, 8, 0), new_run=True)
    engine.tick(session)
    assert engine.tick(session)["drafts_created"] == 0
    assert session.scalar(select(func.count()).select_from(AlertEvent)) == 1
    assert session.scalar(select(func.count()).select_from(AlertRecipient)) == 2
    assert kinds(session, "draft_created") == 1


def test_a_person_who_joins_later_is_added_to_the_open_draft(session, fake_radar):
    setup_people(session, fake_radar)
    clock.set_replay(session, utc(2026, 7, 27, 8, 0), new_run=True)
    engine.tick(session)
    fake_radar[(24.70, 89.76)] = (50.0, 50.0, 50.0)
    add_person(session, "device-late", 24.70, 89.76)
    out = engine.tick(session)
    assert out["drafts_created"] == 0 and out["recipients_added"] == 1
    assert kinds(session, "recipient_added") == 1


def test_decided_events_are_never_drafted_again_in_the_same_run(session, fake_radar):
    setup_people(session, fake_radar)
    clock.set_replay(session, utc(2026, 7, 27, 8, 0), new_run=True)
    engine.tick(session)
    ev = session.scalars(select(AlertEvent)).one()
    lifecycle.reject(session, ev.id, "volunteer", "testing")
    assert engine.tick(session)["drafts_created"] == 0
    # a new replay run may draft it again (rehearsals)
    clock.set_replay(session, utc(2026, 7, 27, 8, 0), new_run=True)
    assert engine.tick(session)["drafts_created"] == 1


def test_a_newer_pass_replaces_an_undecided_older_draft(session, fake_radar):
    setup_people(session, fake_radar)
    clock.set_replay(session, utc(2026, 7, 20, 8, 0), new_run=True)        # 12 Jul pass is the newest
    engine.tick(session)
    clock.set_replay(session, utc(2026, 7, 27, 8, 0))                       # 24 Jul pass published
    engine.tick(session)
    states = {e.event_key: e.state for e in session.scalars(select(AlertEvent))}
    assert states == {"069A_20260712": "rejected", "069A_20260724": "drafted"}
    old = session.scalars(select(AlertEvent).where(AlertEvent.event_key == "069A_20260712")).one()
    assert "newer" in (old.rejected_reason or "")


def test_no_radar_alert_inside_the_gap_from_an_old_picture(session, fake_radar):
    setup_people(session, fake_radar)
    clock.set_replay(session, utc(2026, 8, 9, 0, 0), new_run=True)          # 15 days after the 24 Jul pass
    out = engine.tick(session)
    assert out["drafts_created"] == 0
    assert any("older" in k for k in next(r for r in out["rules"] if r["rule"] == "radar")["reasons"])


def test_river_and_rain_events(session, fake_radar):
    add_person(session, "device-near", *NEAR)
    as_of = utc(2026, 8, 9, 3, 0)
    session.add(RiverReading(station="Kazipur", valid_utc=as_of, level_m=14.55, kind="observed", lead_days=0,
                             issued_utc=as_of - dt.timedelta(hours=2), source_url="http://x", entered_by="t"))
    session.add(RainDaily(date="2026-08-08", mm=81.0, source="NASA IMERG test", visible_utc=as_of - dt.timedelta(hours=1)))
    session.flush()
    clock.set_replay(session, as_of, new_run=True)
    assert engine.tick(session)["drafts_created"] == 2
    got = {e.rule: e for e in session.scalars(select(AlertEvent))}
    assert set(got) == {"river", "rain"}
    assert got["river"].event_key == "Kazipur_2026-08-09" and got["rain"].event_key == "area_2026-08-08"
    assert "14.55" in got["river"].recipients[0].message_en and "81.0" in got["rain"].recipients[0].message_en


# ---------------------------------------------------------------- life cycle
def drafted(session, fake_radar):
    people = setup_people(session, fake_radar)
    clock.set_replay(session, utc(2026, 7, 27, 8, 0), new_run=True)
    engine.tick(session)
    return session.scalars(select(AlertEvent)).one(), people


def test_nothing_is_sent_without_approval(session, fake_radar):
    ev, _ = drafted(session, fake_radar)
    lifecycle.sweep(session)
    assert session.scalar(select(func.count()).select_from(Delivery)) == 0
    assert all(r.state == "queued" for r in ev.recipients)


def test_approval_sends_and_writes_the_ledger(session, fake_radar):
    ev, _ = drafted(session, fake_radar)
    lifecycle.approve(session, ev.id, "Volunteer A")
    assert ev.state == "sent" and ev.approved_by == "Volunteer A"
    assert all(r.state == "sent" and r.sent_utc for r in ev.recipients)
    assert kinds(session, "approved") == 1 and kinds(session, "sent") == 2
    with pytest.raises(lifecycle.LifecycleError):
        lifecycle.approve(session, ev.id, "Volunteer B")              # only once


def test_late_draft_never_sends_by_itself_but_can_still_be_approved(session, fake_radar):
    ev, _ = drafted(session, fake_radar)
    later = utcnow() + dt.timedelta(seconds=settings.APPROVAL_WINDOW_S + 5)
    assert lifecycle.sweep(session, later)["late"] == 1
    assert ev.state == "late" and session.scalar(select(func.count()).select_from(Delivery)) == 0
    assert lifecycle.sweep(session, later)["late"] == 0               # one ledger row, not one per sweep
    assert kinds(session, "late") == 1
    lifecycle.approve(session, ev.id, "Volunteer A")
    assert ev.state == "sent"


def test_rejection_needs_no_send_and_is_final(session, fake_radar):
    ev, _ = drafted(session, fake_radar)
    lifecycle.reject(session, ev.id, "Volunteer A", "radar range too wide")
    assert ev.state == "rejected" and kinds(session, "rejected") == 1
    with pytest.raises(lifecycle.LifecycleError):
        lifecycle.approve(session, ev.id, "Volunteer A")


def test_ack_reply_and_close(session, fake_radar):
    ev, (near, edge, _) = drafted(session, fake_radar)
    lifecycle.approve(session, ev.id, "Volunteer A")
    r_near = next(r for r in ev.recipients if r.person_id == near.id)
    r_edge = next(r for r in ev.recipients if r.person_id == edge.id)
    lifecycle.ack(session, r_near.id, "device-near")
    lifecycle.ack(session, r_near.id, "device-near")                  # idempotent
    assert r_near.state == "acked" and kinds(session, "acked") == 1
    lifecycle.reply(session, r_near.id, "device-near", Reply.safe, Channel.in_app)
    lifecycle.reply(session, r_near.id, "device-near", Reply.safe, Channel.in_app)   # same answer: no new row
    assert r_near.state == RecipientState.replied_safe.value and kinds(session, "reply_safe") == 1
    lifecycle.reply(session, r_edge.id, "device-edge", Reply.help, Channel.call_sim)
    assert ev.state == "sent"                                          # a help request keeps the event open
    lifecycle.callback_done(session, r_edge.id, "Volunteer A")
    assert ev.state == EventState.closed.value and kinds(session, "closed") == 1 and kinds(session, "callback_done") == 1


def test_a_reply_from_another_device_is_refused(session, fake_radar):
    ev, (near, _, _) = drafted(session, fake_radar)
    lifecycle.approve(session, ev.id, "Volunteer A")
    rec = next(r for r in ev.recipients if r.person_id == near.id)
    with pytest.raises(lifecycle.LifecycleError):
        lifecycle.reply(session, rec.id, "device-edge", Reply.safe, Channel.in_app)


def test_drafts_cannot_be_answered(session, fake_radar):
    ev, _ = drafted(session, fake_radar)
    with pytest.raises(lifecycle.LifecycleError):
        lifecycle.reply(session, ev.recipients[0].id, "device-near", Reply.safe, Channel.in_app)


def test_at_most_two_retries_then_no_reply_final(session, fake_radar):
    ev, _ = drafted(session, fake_radar)
    lifecycle.approve(session, ev.id, "Volunteer A")
    step = dt.timedelta(seconds=settings.RETRY_AFTER_S + 1)
    t = utcnow()
    assert lifecycle.sweep(session, t + dt.timedelta(seconds=5)) == {"late": 0, "retried": 0, "no_reply_final": 0}
    t += step
    assert lifecycle.sweep(session, t)["retried"] == 2
    t += step
    assert lifecycle.sweep(session, t)["retried"] == 2
    t += step
    out = lifecycle.sweep(session, t)
    assert out["retried"] == 0 and out["no_reply_final"] == 2
    assert all(r.retry_count == settings.MAX_RETRIES and r.state == "no_reply_final" for r in ev.recipients)
    assert ev.state == "closed" and kinds(session, "retry") == 4
    assert session.scalar(select(func.count()).select_from(Delivery)) == 6      # 2 people x (1 send + 2 retries)


def test_a_reply_stops_the_retries(session, fake_radar):
    ev, (near, _, _) = drafted(session, fake_radar)
    lifecycle.approve(session, ev.id, "Volunteer A")
    rec = next(r for r in ev.recipients if r.person_id == near.id)
    lifecycle.reply(session, rec.id, "device-near", Reply.safe, Channel.in_app)
    lifecycle.sweep(session, utcnow() + dt.timedelta(seconds=settings.RETRY_AFTER_S + 1))
    assert rec.retry_count == 0


def test_a_failing_channel_is_recorded_and_the_app_channel_still_delivers(session, fake_radar):
    fake_radar[(24.69, 89.75)] = (100.0, 100.0, 100.0)
    add_person(session, "device-push", 24.69, 89.75, channels=["in_app", "push", "email", "sms_sim"], email="a@b.org")
    clock.set_replay(session, utc(2026, 7, 27, 8, 0), new_run=True)
    engine.tick(session)
    ev = session.scalars(select(AlertEvent)).one()
    lifecycle.approve(session, ev.id, "Volunteer A")
    res = {d.channel: d.result for d in session.scalars(select(Delivery))}
    assert res == {"in_app": "ok", "push": "failed", "email": "failed", "sms_sim": "ok"}   # no keys, no SMTP in tests
    assert ev.recipients[0].state == "sent"
    assert kinds(session, "send_failed") == 2


# ---------------------------------------------------------------- ledger
def test_impact_numbers_are_counts_of_ledger_rows(session, fake_radar):
    ev, (near, edge, _) = drafted(session, fake_radar)
    lifecycle.approve(session, ev.id, "Volunteer A")
    r_near = next(r for r in ev.recipients if r.person_id == near.id)
    r_edge = next(r for r in ev.recipients if r.person_id == edge.id)
    lifecycle.ack(session, r_near.id, "device-near")
    lifecycle.reply(session, r_near.id, "device-near", Reply.safe, Channel.in_app)
    lifecycle.reply(session, r_edge.id, "device-edge", Reply.help, Channel.in_app)
    out = ledger.impact(session, ev.scope)
    assert (out["drafts_created"], out["approved"], out["alerts_sent"], out["acknowledged"]) == (1, 1, 2, 1)
    assert (out["replies_safe"], out["replies_help"], out["callbacks_done"]) == (1, 1, 0)
    assert out["sends_ok_by_channel"] == {"in_app": 2}
    assert out["median_minutes_input_to_approval"] is not None
    assert ledger.impact(session, "live")["drafts_created"] == 0          # scopes never mix


def test_unknown_ledger_kind_is_refused(session):
    with pytest.raises(ValueError):
        ledger.write(session, "live", "made_up_kind")
