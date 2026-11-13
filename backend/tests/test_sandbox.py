"""The guided demo, end to end, on the real deploy data (deploy_data/kazipur): no fake inputs.

Skipped when the data folder has not been built (python -m jobs.build_backend_data).
"""
from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

DATA = Path(__file__).resolve().parents[1] / "deploy_data"
pytestmark = pytest.mark.skipif(not (DATA / "kazipur" / "radar_rule" / "index.json").exists(),
                                reason="deploy_data not built")


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("DELTASAR_OUTPUTS", str(DATA))
    monkeypatch.setenv("LIVE_INPUTS", "0")
    from src import config
    from src.alerts import settings
    importlib.reload(config)
    importlib.reload(settings)
    from src.alerts import inputs, sandbox
    monkeypatch.setattr(settings, "AOI_OUT", DATA / "kazipur")
    monkeypatch.setattr(settings, "RADAR_RULE_DIR", DATA / "kazipur" / "radar_rule")
    inputs._load_index.cache_clear()
    sandbox._households_file.cache_clear()
    from src.api import app as app_mod
    with TestClient(app_mod.app) as c:
        yield c


def test_guided_loop(client):
    r = client.post("/api/v1/sandbox")
    assert r.status_code == 200, r.text
    sid, me = r.json()["sandbox_id"], r.json()["visitor_device_id"]
    snap = r.json()["snapshot"]
    assert snap["replay"] and snap["as_of_local"].startswith("2026-07-26T14:00")
    assert len(snap["people"]) == 6
    assert snap["events"] == []

    # 1. NASA publishes the 24 Jul pass
    r = client.post(f"/api/v1/sandbox/{sid}/next-event").json()
    assert "24 Jul 2026" in r["label"] or "25 Jul 2026" in r["label"]
    assert r["radar"]["date"] == "20260724"

    # 2. the rule drafts one radar alert, never sends it
    r = client.post(f"/api/v1/sandbox/{sid}/tick").json()
    radar = [e for e in r["events"] if e["rule"] == "radar"]
    assert len(radar) == 1 and radar[0]["state"] == "drafted"
    n = len(radar[0]["recipients"])
    assert 3 <= n <= 5                                     # households beyond 1 km stay silent
    silent = [p for p in r["people"] if not p["rules"]["radar"]["fired"]]
    assert silent and all("beyond" in p["rules"]["radar"]["reason"] for p in silent)
    assert client.get(f"/api/v1/people/{me}/alerts").json() == []      # a draft is invisible to the phone

    # 3. volunteer approves; the visitor's phone now has an active alert
    r = client.post(f"/api/v1/sandbox/{sid}/events/{radar[0]['event_id']}/approve", json={"volunteer": "Judge"}).json()
    assert r["event"]["state"] == "sent"
    st = client.get(f"/api/v1/people/{me}/status").json()
    assert st["status"] == "alert" and st["replay"] is True
    rid = st["active_alert"]["recipient_id"]
    assert "মিনিট" in st["active_alert"]["message_bn"]

    # 4. the phone answers "help"; the console shows it; call-back closes it
    assert client.post(f"/api/v1/alerts/{rid}/reply", json={"device_id": me, "reply": "help", "via": "in_app"}).status_code == 200
    r = client.post(f"/api/v1/sandbox/{sid}/simulate-replies").json()
    assert r["impact"]["replies_help"] >= 1 and r["impact"]["replies_safe"] >= 1
    r = client.post(f"/api/v1/sandbox/{sid}/callbacks/{rid}/done", json={"volunteer": "Judge"}).json()
    assert r["impact"]["callbacks_done"] == 1

    # 5. radar gap + the 75.2 mm day: rain rule stays silent, with its numbers
    r = client.put(f"/api/v1/sandbox/{sid}/clock", json={"mode": "replay", "preset": "gap_rain"}).json()
    assert r["in_radar_gap"] is True
    rain = r["people"][0]["rules"]["rain"]
    assert rain["fired"] is False and rain["values"]["rain_mm"] == 75.2 and rain["values"]["limit_mm"] == 76

    # another visitor's sandbox is untouched, and the shared console clock never moved
    other = client.post("/api/v1/sandbox").json()
    assert other["snapshot"]["events"] == []
    assert client.get(f"/api/v1/sandbox/{sid}/events/x").status_code in (404, 405)


def test_point_report(client):
    r = client.get("/api/v1/point", params={"lat": 24.70227, "lon": 89.74656}).json()
    assert r["covered"] and len(r["passes"]) >= 10
    assert client.get("/api/v1/point", params={"lat": 23.0, "lon": 90.0}).json()["covered"] is False
    h = client.get("/api/v1/health").json()
    assert h["radar_passes"] >= 10 and h["rain_days"] > 100
