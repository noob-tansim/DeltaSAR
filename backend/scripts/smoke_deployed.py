"""Smoke test of a deployed DeltaSAR: the API on Render and the web app on Vercel, end to end.

    python scripts/smoke_deployed.py --api https://deltasar-api.onrender.com --web https://deltasar.vercel.app

Runs the guided demo through the public API (a sandbox is created and expires by itself), checks the database
is Postgres, the assistant status, and that the web app serves its pages and data. Exit code 0 = all passed.
"""
from __future__ import annotations

import argparse
import sys
import time

import requests

OK, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def check(name: str, fn) -> object:
    t0 = time.time()
    try:
        out = fn()
        results.append((OK, name, f"{time.time() - t0:.1f}s"))
        return out
    except Exception as exc:                     # report and continue: one failure should not hide the others
        results.append((FAIL, name, f"{type(exc).__name__}: {exc}"[:200]))
        return None


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True)
    ap.add_argument("--web")
    a = ap.parse_args()
    api = a.api.rstrip("/")
    s = requests.Session()

    def health():
        r = s.get(f"{api}/api/v1/health", timeout=120)      # first call may wake a sleeping free instance
        j = r.json()
        assert r.ok and j["ok"], j
        assert j["database"] == "postgres", f"database is {j['database']} (expected Supabase Postgres)"
        assert j["radar_passes"] >= 10 and j["rain_days"] > 100, j
        return j
    check("API health, Postgres, data loaded", health)

    def loop():
        c = s.post(f"{api}/api/v1/sandbox", timeout=60).json()
        sid, me = c["sandbox_id"], c["visitor_device_id"]
        nxt = s.post(f"{api}/api/v1/sandbox/{sid}/next-event", timeout=60).json()
        assert nxt["radar"]["date"] == "20260724", nxt.get("radar")
        t = s.post(f"{api}/api/v1/sandbox/{sid}/tick", timeout=60).json()
        ev = next(e for e in t["events"] if e["rule"] == "radar")
        assert ev["state"] == "drafted" and 3 <= len(ev["recipients"]) <= 5
        s.post(f"{api}/api/v1/sandbox/{sid}/events/{ev['event_id']}/approve", json={"volunteer": "smoke test"}, timeout=60).raise_for_status()
        st = s.get(f"{api}/api/v1/people/{me}/status", timeout=60).json()
        assert st["status"] == "alert", st["status"]
        rid = st["active_alert"]["recipient_id"]
        s.post(f"{api}/api/v1/alerts/{rid}/reply", json={"device_id": me, "reply": "help", "via": "in_app"}, timeout=60).raise_for_status()
        done = s.post(f"{api}/api/v1/sandbox/{sid}/callbacks/{rid}/done", json={"volunteer": "smoke test"}, timeout=60).json()
        assert done["impact"]["replies_help"] >= 1 and done["impact"]["callbacks_done"] >= 1
        gap = s.put(f"{api}/api/v1/sandbox/{sid}/clock", json={"mode": "replay", "preset": "gap_rain"}, timeout=60).json()
        assert gap["in_radar_gap"] and gap["people"][0]["rules"]["rain"]["fired"] is False
        return sid
    check("Guided demo loop (draft, approve, alert, help, call-back, gap)", loop)
    check("Point report", lambda: s.get(f"{api}/api/v1/point", params={"lat": 24.70227, "lon": 89.74656}, timeout=60).json()["covered"] or 1 / 0)
    check("Assistant status", lambda: s.get(f"{api}/api/v1/ask/status", timeout=30).json())

    if a.web:
        web = a.web.rstrip("/")
        for path in ("/", "/demo", "/explore", "/app", "/methods", "/data/season.json", "/data/story.json", "/manifest.webmanifest"):
            check(f"Web {path}", lambda p=path: (lambda r: r.ok or 1 / 0)(s.get(f"{web}{p}", timeout=60)))

        def cors():
            r = s.options(f"{api}/api/v1/sandbox", headers={"Origin": web, "Access-Control-Request-Method": "POST"}, timeout=60)
            allowed = r.headers.get("access-control-allow-origin")
            assert allowed in (web, "*"), f"CORS does not allow {web}: {allowed}"
        check("CORS allows the web app", cors)

    width = max(len(n) for _, n, _ in results)
    for status, name, detail in results:
        print(f"{status}  {name.ljust(width)}  {detail}")
    failed = [r for r in results if r[0] == FAIL]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
