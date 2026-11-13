"""Bangla speech for devices that have no Bangla voice: Google Gemini text-to-speech, cached in the database.

It only reads text aloud: the alert sentences are fixed templates filled by code and approved by a volunteer, so
the model writes nothing. Each sentence is generated once and stored (table tts_cache), so it survives restarts and
plays instantly the next time. Guardrails: Bangla text only, length cap, per-visitor rate limit.
"""
from __future__ import annotations

import hashlib
import io
import os
import re
import threading
import time
import wave
from collections import deque
from typing import Any

import requests
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from src.alerts.db import TtsCache, session_scope

router = APIRouter(prefix="/api/v1/tts", tags=["speech"])

URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
BENGALI = re.compile(r"[ঀ-৿]")
PER_IP = int(os.environ.get("TTS_PER_IP_PER_10MIN", 30))
CACHE_VERSION = "v2"   # v1 clips were made with a spoken instruction in front of the sentence; never serve them
_lock = threading.Lock()
_hits: dict[str, deque[float]] = {}


def key() -> str:
    return os.environ.get("GEMINI_API_KEY", "").strip()


def models() -> list[str]:
    raw = os.environ.get("GEMINI_TTS_MODELS", "gemini-3.8-flash-tts,gemini-3.8-flash-lite-tts,gemini-3.1-flash-tts-preview")
    return [m.strip() for m in raw.split(",") if m.strip()]


def voice() -> str:
    return os.environ.get("GEMINI_TTS_VOICE", "Kore").strip()


class SpeakIn(BaseModel):
    text: str = Field(min_length=2, max_length=700)


def _rate_ok(ip: str) -> bool:
    now = time.time()
    with _lock:
        q = _hits.setdefault(ip, deque())
        while q and now - q[0] > 600:
            q.popleft()
        if len(q) >= PER_IP:
            return False
        q.append(now)
        return True


def _as_wav(data: bytes, mime: str) -> bytes:
    """Gemini returns either a finished WAV file or raw 16-bit PCM (audio/L16;rate=24000)."""
    if data[:4] == b"RIFF":
        return data
    rate = int(m.group(1)) if (m := re.search(r"rate=(\d+)", mime or "")) else 24000
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(data)
    return buf.getvalue()


def synthesize(text: str) -> bytes:
    import base64
    last = "no model answered"
    for m in models():
        try:
            r = requests.post(URL.format(model=m), timeout=60, headers={"x-goog-api-key": key(), "Content-Type": "application/json"},
                              json={"contents": [{"parts": [{"text": text}]}],   # the sentence only: any instruction here can be read aloud
                                    "generationConfig": {"responseModalities": ["AUDIO"],
                                                         "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice()}}}}})
        except requests.RequestException as exc:
            last = f"{m}: {type(exc).__name__}"
            continue
        if r.status_code != 200:
            last = f"{m}: HTTP {r.status_code}"
            continue
        part = ((r.json().get("candidates") or [{}])[0].get("content") or {}).get("parts", [{}])[0].get("inlineData") or {}
        if part.get("data"):
            return _as_wav(base64.b64decode(part["data"]), part.get("mimeType", ""))
        last = f"{m}: no audio"
    raise HTTPException(502, f"Speech is not available right now ({last}).")


@router.get("/status")
def status() -> dict[str, Any]:
    return {"enabled": bool(key()), "models": models() if key() else None, "voice": voice()}


@router.post("")
def speak(body: SpeakIn, request: Request) -> Response:
    if not key():
        raise HTTPException(503, "Speech is switched off on this server (no GEMINI_API_KEY).")
    text = " ".join(body.text.split())
    if len(BENGALI.findall(text)) < 4:
        raise HTTPException(422, "Only Bangla text is read aloud here.")
    digest = hashlib.sha256(f"{CACHE_VERSION}|{voice()}|{text}".encode()).hexdigest()
    with session_scope() as s:
        row = s.get(TtsCache, digest)
        if row is not None:
            return Response(row.audio, media_type="audio/wav", headers={"Cache-Control": "public, max-age=86400", "X-Cache": "hit"})
    fwd = request.headers.get("x-forwarded-for", "")
    ip = (fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?"))[:64]
    if not _rate_ok(ip):
        raise HTTPException(429, "Too many new sentences in a short time; please wait a few minutes.")
    audio = synthesize(text)
    with session_scope() as s:
        if s.get(TtsCache, digest) is None:
            s.add(TtsCache(key=digest, text=text[:700], audio=audio))
    return Response(audio, media_type="audio/wav", headers={"Cache-Control": "public, max-age=86400", "X-Cache": "miss"})


def cached_count() -> int:
    with session_scope() as s:
        return len(s.scalars(select(TtsCache.key)).all())
