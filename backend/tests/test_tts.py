"""Bangla speech endpoint: Bangla only, cached in the database, Gemini mocked."""
from __future__ import annotations

import base64

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import tts_routes


def client() -> TestClient:
    app = FastAPI()
    app.include_router(tts_routes.router)
    return TestClient(app)


def test_off_without_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert client().post("/api/v1/tts", json={"text": "এটি একটি পরীক্ষা"}).status_code == 503


def test_bangla_only_and_cached(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    calls = []
    pcm = bytes(4800)                      # 0.1 s of silence, 16-bit mono at 24 kHz

    class R:
        status_code = 200

        def json(self):
            return {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "audio/L16;rate=24000",
                                                                          "data": base64.b64encode(pcm).decode()}}]}}]}

    def fake_post(*args, **kwargs):
        calls.append(1)
        return R()

    monkeypatch.setattr(tts_routes.requests, "post", fake_post)
    tts_routes._hits.clear()
    c = client()
    assert c.post("/api/v1/tts", json={"text": "Hello world, English only"}).status_code == 422
    r1 = c.post("/api/v1/tts", json={"text": "নিরাপদ থাকলে ১ চাপুন।"})
    assert r1.status_code == 200 and r1.content[:4] == b"RIFF" and r1.headers["x-cache"] == "miss"
    r2 = c.post("/api/v1/tts", json={"text": "নিরাপদ  থাকলে ১ চাপুন।"})       # same sentence, extra space
    assert r2.headers["x-cache"] == "hit" and len(calls) == 1
