"""Ask DeltaSAR: a question-and-answer assistant on the website, using Google's Gemini API (free tier).

Guardrails, because the project's rule is "no AI in the alert path, no number without a source":
- It answers only from the curated facts in ask_facts.md (every number there comes from the project's files).
- It is never part of the alert path: it cannot draft, approve or send anything, and it never gives warnings.
- The key stays on the server (GEMINI_API_KEY); questions are limited in length and rate; nothing is stored.
Without a key the route says it is switched off; the website then shows its built-in FAQ only.
"""
from __future__ import annotations

import os
import re
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Literal

import requests
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/ask", tags=["assistant"])

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
FACTS = (Path(__file__).with_name("ask_facts.md")).read_text(encoding="utf-8")
PER_IP = int(os.environ.get("ASK_PER_IP_PER_10MIN", 15))
GLOBAL_PER_HOUR = int(os.environ.get("ASK_GLOBAL_PER_HOUR", 300))
_lock = threading.Lock()
_ip_hits: dict[str, deque[float]] = {}
_all_hits: deque[float] = deque()


def key() -> str:
    return os.environ.get("GEMINI_API_KEY", "").strip()


def model() -> str:
    return os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip()


SYSTEM = """You are "Ask DeltaSAR", the assistant on the DeltaSAR / বন্যা সাথী website (NASA Space Apps 2026, "Dancing with the SARs").
Rules:
1. Answer ONLY from the FACTS below. If the FACTS do not contain the answer, say so plainly and suggest the Methods page (/methods). Never guess.
2. Never invent or change a number, date, place or name. When you give a number, say where it comes from (for example "NISAR track 069A" or "NASA IMERG").
3. You are not a warning service. Never say whether anyone is or will be safe, never forecast floods, never tell people to evacuate. For any danger or emergency, say: in an emergency call 999; official flood forecasts come from FFWC and BMD; call 1090 (free) for the government's voice forecast.
4. Reply in {lang}. {lang_rule}
5. Be brief: at most 120 words, plain sentences, no markdown tables.

FACTS:
{facts}"""

LANG_RULE = {
    "bn": "Use simple, everyday Bangla (বাংলা) and Bangla digits; keep technical names like NISAR, HH, FFWC in Latin letters.",
    "en": "Use plain English for a general audience.",
}


_BN = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_NUM = re.compile(r"\d+(?:[.,]\d+)*")


def _nums(text: str) -> set[str]:
    """Numbers in a text, normalised: Bangla digits to Latin, thousands commas dropped, trailing .0 dropped."""
    out = set()
    for m in _NUM.findall(text.translate(_BN)):
        v = m.replace(",", "")
        out.add(v[:-2] if v.endswith(".0") else v)
    return out


FACT_NUMS = _nums(FACTS) | {str(i) for i in range(0, 13)}


def untraced_numbers(answer: str) -> list[str]:
    """Build-guide rule: every number the model states must come from the facts. Returns the ones that do not."""
    return sorted(n for n in _nums(answer) if n not in FACT_NUMS)


class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    lang: Literal["bn", "en"] = "en"
    history: list[dict[str, str]] = Field(default_factory=list, max_length=6)


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return (fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?"))[:64]


def _rate_ok(ip: str, now: float | None = None) -> bool:
    now = now or time.time()
    with _lock:
        q = _ip_hits.setdefault(ip, deque())
        while q and now - q[0] > 600:
            q.popleft()
        while _all_hits and now - _all_hits[0] > 3600:
            _all_hits.popleft()
        if len(q) >= PER_IP or len(_all_hits) >= GLOBAL_PER_HOUR:
            return False
        q.append(now)
        _all_hits.append(now)
        return True


def build_request(body: AskIn) -> dict[str, Any]:
    contents: list[dict[str, Any]] = []
    for turn in body.history[-6:]:
        role = "model" if turn.get("role") == "assistant" else "user"
        text = (turn.get("text") or "")[:800]
        if text:
            contents.append({"role": role, "parts": [{"text": text}]})
    contents.append({"role": "user", "parts": [{"text": body.question}]})
    return {
        "system_instruction": {"parts": [{"text": SYSTEM.format(lang="Bangla" if body.lang == "bn" else "English",
                                                                lang_rule=LANG_RULE[body.lang], facts=FACTS)}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 700},
    }


@router.get("/status")
def status() -> dict[str, Any]:
    return {"enabled": bool(key()), "model": model() if key() else None, "provider": "Google Gemini API"}


@router.post("")
def ask(body: AskIn, request: Request) -> dict[str, Any]:
    if not key():
        return {"enabled": False, "answer": None,
                "note": "The assistant is switched off on this server (no GEMINI_API_KEY). The built-in questions still work."}
    if not _rate_ok(_client_ip(request)):
        raise HTTPException(429, "Too many questions in a short time; please wait a few minutes.")
    try:
        r = requests.post(GEMINI_URL.format(model=model()), json=build_request(body), timeout=30,
                          headers={"x-goog-api-key": key(), "Content-Type": "application/json"})
    except requests.RequestException as exc:
        raise HTTPException(502, f"The assistant could not be reached ({type(exc).__name__}).")
    if r.status_code != 200:
        raise HTTPException(502, f"The assistant answered with HTTP {r.status_code}.")
    data = r.json()
    parts = ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise HTTPException(502, "The assistant gave no answer; please rephrase.")
    bad = untraced_numbers(text)
    return {"enabled": True, "answer": text, "model": model(), "grounded_on": "ask_facts.md",
            "numbers_verified": not bad, "untraced_numbers": bad,
            "note": "AI answer from the project's published facts. It may be wrong; it is not a warning."}
