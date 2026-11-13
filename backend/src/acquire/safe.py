"""Offline safety net: live API first, then local cache, then a committed demo fixture.

Set OFFLINE=1 to force cache/fixture (use this to rehearse the demo without Wi-Fi).
"""
from __future__ import annotations

import hashlib
import json
import os

import requests

from src.config import CACHE, FIXTURES

(CACHE / "api").mkdir(parents=True, exist_ok=True)


def fetch_json(url: str, params: dict | None = None, name: str | None = None, timeout: int = 30):
    """Returns (data, mode) where mode is 'live', 'cache' or 'fixture'."""
    offline = os.getenv("OFFLINE") == "1"
    key = name or hashlib.md5(f"{url}{sorted((params or {}).items())}".encode()).hexdigest()
    cached = CACHE / "api" / f"{key}.json"
    fixture = FIXTURES / f"{key}.json"

    if not offline:
        try:
            r = requests.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            data = r.json()
            cached.write_text(json.dumps(data, indent=1), encoding="utf-8")
            return data, "live"
        except Exception as exc:  # network down, API error, bad JSON
            print(f"[safe] live call failed for {key}: {exc!r}; trying cache")

    if cached.exists():
        return json.loads(cached.read_text(encoding="utf-8")), "cache"
    if fixture.exists():
        return json.loads(fixture.read_text(encoding="utf-8")), "fixture"
    raise FileNotFoundError(f"No live, cache or fixture data for '{key}'")
