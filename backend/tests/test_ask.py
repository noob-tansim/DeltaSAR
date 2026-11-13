"""Ask DeltaSAR: off without a key; request shape; number post-check; rate limit. Gemini itself is mocked."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import ask_routes


def client() -> TestClient:
    app = FastAPI()
    app.include_router(ask_routes.router)
    return TestClient(app)


def test_off_without_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    c = client()
    assert c.get("/api/v1/ask/status").json()["enabled"] is False
    r = c.post("/api/v1/ask", json={"question": "What is NISAR?", "lang": "en"}).json()
    assert r["enabled"] is False and r["answer"] is None


def test_numbers_must_trace_to_facts():
    assert ask_routes.untraced_numbers("Between 187 and 232 hectares, confirmed on 16 Oct 2026.") == []
    assert ask_routes.untraced_numbers("৭১২টি ঘরবাড়ি ১০০ মিটারের মধ্যে") == []          # Bangla digits are checked too
    assert ask_routes.untraced_numbers("About 1,234 people were evacuated.") == ["1234"]


def test_request_and_answer(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    seen = {}

    class R:
        status_code = 200
        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "NISAR saw 187 to 232 ha of bank loss (track 069A). About 1,234 people moved."}]}}]}

    def fake_post(url, json, timeout, headers):
        seen.update(url=url, body=json, headers=headers)
        return R()

    monkeypatch.setattr(ask_routes.requests, "post", fake_post)
    ask_routes._ip_hits.clear(); ask_routes._all_hits.clear()
    r = client().post("/api/v1/ask", json={"question": "নদীভাঙন কত?", "lang": "bn"}).json()
    assert r["enabled"] and "187" in r["answer"]
    assert r["numbers_verified"] is False and r["untraced_numbers"] == ["1234"]
    assert seen["headers"]["x-goog-api-key"] == "test-key"                 # key in a header, never in the URL
    assert "key=" not in seen["url"]
    sys_text = seen["body"]["system_instruction"]["parts"][0]["text"]
    assert "Bangla" in sys_text and "FACTS" in sys_text and "999" in sys_text


def test_rate_limit(monkeypatch):
    ask_routes._ip_hits.clear(); ask_routes._all_hits.clear()
    ok = [ask_routes._rate_ok("1.2.3.4", now=1000.0 + i) for i in range(ask_routes.PER_IP + 1)]
    assert all(ok[:-1]) and ok[-1] is False
    assert ask_routes._rate_ok("1.2.3.4", now=1000.0 + 700)              # window passed


def test_falls_back_when_a_model_is_busy(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODELS", "busy-model,good-model")
    calls = []

    class Busy:
        status_code = 503
        def json(self):
            return {}

    class Good:
        status_code = 200
        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "HH separates water best."}]}}]}

    def fake_post(url, json, timeout, headers):
        calls.append(url)
        return Busy() if "busy-model" in url else Good()

    monkeypatch.setattr(ask_routes.requests, "post", fake_post)
    ask_routes._ip_hits.clear(); ask_routes._all_hits.clear()
    r = client().post("/api/v1/ask", json={"question": "Which polarisation?", "lang": "en"}).json()
    assert r["model"] == "good-model" and len(calls) == 2
