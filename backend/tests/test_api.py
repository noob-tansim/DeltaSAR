"""The HTTP layer: console token, joining, the full loop through the API, and removing a person's details."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.alerts import db
from src.api import alerts_routes

AUTH = {"Authorization": "Bearer test-token"}
PERSON = {"home_lat": 24.69, "home_lon": 89.75, "consent": True, "months": list(range(1, 13)),
          "display_name": "Tester", "email": "t@example.org", "channels": ["in_app", "email", "sms_sim"]}


@pytest.fixture()
def client(fake_radar):
    fake_radar[(24.69, 89.75)] = (200.0, 150.0, 100.0)
    app = FastAPI()
    app.include_router(alerts_routes.router)
    app.include_router(alerts_routes.console)
    app.dependency_overrides[alerts_routes.db] = db.get_session
    return TestClient(app)


def test_console_needs_the_token(client):
    assert client.get("/api/v1/console/clock").status_code == 401
    assert client.get("/api/v1/console/clock", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/api/v1/console/clock", headers=AUTH).status_code == 200
    assert client.post("/api/v1/console/tick").status_code == 401


def test_join_validates_ranges(client):
    assert client.put("/api/v1/people/device-0001", json={**PERSON, "rain_mm": 5}).status_code == 422
    assert client.put("/api/v1/people/device-0001", json={**PERSON, "home_lat": 23.8}).status_code == 422
    assert client.put("/api/v1/people/device-0001", json={**PERSON, "consent": False}).status_code == 422
    assert client.put("/api/v1/people/short", json=PERSON).status_code == 422
    assert client.get("/api/v1/people/device-0001").status_code == 404
    r = client.put("/api/v1/people/device-0001", json=PERSON)
    assert r.status_code == 200 and r.json()["is_demo"] is True and r.json()["rain_mm"] == 76


def test_full_loop_through_the_api(client):
    dev = "device-0001"
    client.put(f"/api/v1/people/{dev}", json=PERSON)
    clock = client.put("/api/v1/console/clock", headers=AUTH,
                       json={"mode": "replay", "as_of_utc": "2026-07-26T08:00:00Z", "new_run": True}).json()
    assert clock["mode"] == "replay" and "20260724" in clock["next_event_label"]
    clock = client.post("/api/v1/console/clock/next-event", headers=AUTH).json()
    assert clock["as_of_utc"].startswith("2026-07-27T07:22")
    tick = client.post("/api/v1/console/tick", headers=AUTH).json()
    assert tick["drafts_created"] == 1 and tick["replay"] is True

    # a draft is invisible to the phone
    assert client.get(f"/api/v1/people/{dev}/alerts").json() == []
    status = client.get(f"/api/v1/people/{dev}/status").json()
    assert status["active_alert"] is None and status["replay"] is True and status["status"] == "watch"

    drafts = client.get("/api/v1/console/drafts", headers=AUTH).json()
    assert len(drafts) == 1 and drafts[0]["recipients"][0]["confidence"] == "sure"
    rid = drafts[0]["recipients"][0]["recipient_id"]
    assert client.get(f"/api/v1/alerts/{rid}").status_code == 404
    assert client.post(f"/api/v1/alerts/{rid}/reply", json={"device_id": dev, "reply": "safe"}).status_code == 409

    ev = client.post(f"/api/v1/console/drafts/{drafts[0]['event_id']}/approve", headers=AUTH, json={"volunteer": "Vol A"}).json()
    assert ev["state"] == "sent" and ev["recipients"][0]["state"] == "sent"
    assert client.post(f"/api/v1/console/drafts/{drafts[0]['event_id']}/approve", headers=AUTH,
                       json={"volunteer": "Vol A"}).status_code == 409

    status = client.get(f"/api/v1/people/{dev}/status").json()
    assert status["status"] == "alert" and status["active_alert"]["recipient_id"] == rid
    alert = client.get(f"/api/v1/alerts/{rid}").json()
    assert alert["message_en"].startswith("REPLAY") and alert["values"]["distance_m"] == 150
    evid = client.get(f"/api/v1/alerts/{rid}/evidence").json()
    assert [r["key"] for r in evid["rows"]] == ["what", "where", "when", "how_sure"]
    assert evid["receipt"]["input"]["granule_id"] == "G_069A_20260724"

    assert client.post(f"/api/v1/alerts/{rid}/ack", json={"device_id": "another-device"}).status_code == 409
    assert client.post(f"/api/v1/alerts/{rid}/ack", json={"device_id": dev}).json()["state"] == "acked"
    assert client.post(f"/api/v1/alerts/{rid}/reply", json={"device_id": dev, "reply": "maybe"}).status_code == 422
    assert client.post(f"/api/v1/alerts/{rid}/reply", json={"device_id": dev, "reply": "help", "via": "call_sim"}).json()["reply"] == "help"

    ev = client.get("/api/v1/console/events", headers=AUTH).json()[0]
    assert ev["recipients"][0]["state"] == "replied_help" and ev["recipients"][0]["callback_done"] is False
    ev = client.post(f"/api/v1/console/callbacks/{rid}/done", headers=AUTH, json={"volunteer": "Vol A"}).json()
    assert ev["state"] == "closed"

    impact = client.get("/api/v1/console/impact", headers=AUTH).json()
    assert (impact["drafts_created"], impact["approved"], impact["replies_help"], impact["callbacks_done"]) == (1, 1, 1, 1)
    assert impact["sends_failed_by_channel"] == {"email": 1}          # SMTP is not configured in tests
    kinds = [row["kind"] for row in client.get("/api/v1/console/ledger", headers=AUTH).json()]
    for k in ("draft_created", "approved", "sent", "send_failed", "acked", "reply_help", "callback_done", "closed"):
        assert k in kinds

    # live mode is a different scope: the replay alert does not show there
    client.put("/api/v1/console/clock", headers=AUTH, json={"mode": "live"})
    assert client.get(f"/api/v1/people/{dev}/status").json()["active_alert"] is None


def test_river_reading_entry_is_range_checked(client):
    body = {"station": "Kazipur", "valid_local": "2026-08-09T06:00:00", "level_m": 13.74, "kind": "observed",
            "source_url": "http://old.ffwc.gov.bd/", "entered_by": "Vol A"}
    assert client.post("/api/v1/console/river-readings", headers=AUTH, json={**body, "level_m": 30}).status_code == 422
    assert client.post("/api/v1/console/river-readings", headers=AUTH, json={**body, "station": "Nowhere"}).status_code == 422
    r = client.post("/api/v1/console/river-readings", headers=AUTH, json=body)
    assert r.status_code == 200 and r.json()["valid_utc"].startswith("2026-08-09T00:00")      # 06:00 Dhaka = 00:00 UTC


def test_delete_removes_contact_details(client):
    dev = "device-0001"
    client.put(f"/api/v1/people/{dev}", json=PERSON)
    assert client.delete(f"/api/v1/people/{dev}").json() == {"removed": True}
    p = client.get(f"/api/v1/people/{dev}").json()
    assert p["email"] is None and p["display_name"] is None and p["channels"] == ["in_app"]
    assert not (p["radar_on"] or p["river_on"] or p["rain_on"])
