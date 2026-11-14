# Project rules

DeltaSAR · বন্যা সাথী — NISAR radar evidence → fixed rules → volunteer approval → spoken alert → counted reply.

1. **No number without a source.** Every value shown or sent traces to a file or API with a receipt (granule, threshold, date).
2. **Fixed code computes; AI never computes.** No language model in `backend/src/compute`, `backend/src/alerts` or the alert path. The website assistant (`src/api/ask_routes.py`) only explains, answers from `ask_facts.md`, and flags any number it cannot trace.
3. **A rule only drafts. A person approves.** Nothing is sent without a volunteer's approval.
4. **No synthetic data.** Gaps stay gaps (radar off 27 Jul – 10 Aug 2026). Replay uses only data published by that moment and says REPLAY. Simulated channels (call, SMS) are labelled.
5. **Typed, with ranges.** Out-of-range input is refused or "unknown", never clipped.
6. **Offline-first demo.** Every live call has a cached fallback; the guided demo must pass with the network cut. `LIVE_INPUTS=0` / `OFFLINE=1` force snapshots.
7. **Keys live in environment variables only** (`.env`, Render, Vercel). Commit `.env.example`, never `.env`.
8. **Calm words, both languages.** No fear words. Always: "Not an official warning. Official forecasts: FFWC, BMD, call 1090." Bangla text is a draft until a native reader checks it.
9. Times are stored in UTC and shown in Asia/Dhaka. Radar passes are named by their UTC acquisition date.
10. **Before you push:** `cd backend && python -m pytest tests -q` and `cd frontend && npm run build`. Live sources: `LIVE_TESTS=1 python -m pytest tests/test_live_sources.py`.
