# DeltaSAR · বন্যা সাথী (Bonna Sathi)

**Live:** https://deltasar.vercel.app · API https://deltasar-api.onrender.com/docs

**Processed data (Google Drive):** https://drive.google.com/drive/folders/1KkCbSMfJ1LOwljZSYkhCsfham1P6ruKF?usp=sharing

**NASA Space Apps Challenge 2026 · Dancing with the SARs · Team Astro Bengalis (Bangladesh)**

NASA-ISRO **NISAR** radar sees the Jamuna through monsoon cloud. **DeltaSAR** turns each pass into a map of where water and riverbank changed, with a receipt for every number. **বন্যা সাথী** carries that evidence to families on the river islands: a volunteer checks every alert, the phone reads it aloud in Bangla, and the family answers *safe* or *help*.

> Radar evidence, a human check, a spoken alert, and a counted reply.

| Page | What it is |
|---|---|
| `/` **Story** | The 2026 season on the Jamuna: cloud vs radar, 13 NISAR passes (newest 9 Nov, VALIDATED), 187–232 ha of riverbank lost (confirmed), drivers, polarisation, honest skill test |
| `/explore` **Explorer** | Every pass and layer, swipe-compare, NASA GIBS live layers, union ranking, a report for any clicked point |
| `/demo` **Live demo** | The whole alert loop on the real 24 Jul 2026 pass, in a private sandbox; scan a QR code to use your own phone |
| `/app` **বন্যা সাথী** | The resident app: Bangla first, voice on every screen, hold-to-reply, works offline. Full-screen on a phone; on a laptop the app sits beside an expanded view of the same area |
| `/console` | Volunteer console for the team's live service (token) |
| `/methods` | Method, validation per pass, every data source and licence, limits, AI use, and a live check of every NASA connection |
| **Ask DeltaSAR** | Assistant on the public pages (English and বাংলা): a fixed FAQ, plus Google Gemini answering only from `ask_facts.md`, with every number checked. Never in the alert path |

The whole site switches between English and বাংলা (top bar).

## Key results (all from the files in this repository)

| | Value | Source |
|---|---|---|
| Mainland riverbank lost, 18 Jun → 4 Oct 2026, confirmed by 16 Oct | **187–232 ha** (38 sites) | `pairs/erosion_069A_interim.json` |
| Buildings within 100 m of a bank that retreated | **712** | `insights.json` |
| Cropland under water at the peak pass (24 Jul) | **39,425 ha** | `insights.json` |
| Water–land contrast, HH vs HV | **9.0–11.6 dB vs 6.8–8.2 dB** | `validation.json` |
| Mean CSI: stage proxy / ML / “same as last pass” | **0.17 / 0.48 / 0.50** (persistence wins 6 of 9) | `validation.json` |
| NASA publication delay, track 069A since late July | **45–71 h** | `data/passes.json` (NASA CMR) |

## Architecture

```
Browser ── static app + data ── Vercel (frontend/)
   │  └─ NASA CMR · GIBS · EONET · POWER, called live from the browser (no key)
   └─ /api/v1 ── Render (backend/, FastAPI in Docker) ── Supabase Postgres
                  rules · drafts · approval · delivery · replies · ledger · guided-demo sandboxes
```

* `backend/src/acquire|compute|pipeline` — the science kit: NISAR GCOV → water, change, bank loss, receipts.
* `backend/src/alerts` — three fixed rules (radar, river, rain), engine, life cycle, ledger, sandboxes.
* `backend/jobs` — data jobs: radar-rule layers (J1), inputs (J2), `build_backend_data`, `build_web_data`.
* `frontend/` — Vite + React + TypeScript + MapLibre; PWA with Web Push.

## Run it locally

```bash
# API (Python 3.11+)
cd backend
pip install -r requirements.txt
python -m pytest tests -q                       # 125 tests; TEST_DATABASE_URL=postgresql://… runs them on Postgres
LIVE_TESTS=1 python -m pytest tests/test_live_sources.py   # 7 tests against live NASA CMR, ASF, GIBS, EONET, POWER, IMERG, FFWC
python scripts/audit_numbers.py                 # every headline number on the site, recomputed from its source file
python scripts/smoke_deployed.py --api https://deltasar-api.onrender.com --web https://deltasar.vercel.app
DELTASAR_OUTPUTS=deploy_data uvicorn src.api.app:app --port 8010

# Web (Node 20+)
cd frontend
npm install
npm run dev                                     # http://localhost:5173 (proxies /api to :8010)
```

Deploy: [docs/DEPLOY.md](docs/DEPLOY.md). Rebuilding the data from the full kit outputs: [docs/HISTORY.md](docs/HISTORY.md).

## What we do not claim

Not real-time (radar about two days after each pass), not a forecast (our model does not beat the last picture), not depth, not an official warning (official forecasts: FFWC, BMD, call **1090**). NISAR data before 25 Oct 2026 is PROVISIONAL. The radar gap 27 Jul – 10 Aug 2026 is shown, never filled. Voice calls and SMS are simulated and labelled; everyone in the demo is a demo participant.

## Licence and data

Code: Apache-2.0 ([LICENSE](LICENSE)). Data keep their own licences: [NOTICE.md](NOTICE.md). AI use: [docs/AI_USE.md](docs/AI_USE.md).

The processed data (the outputs of our NISAR processing, too large for this repository) are in a public Google Drive folder: https://drive.google.com/drive/folders/1KkCbSMfJ1LOwljZSYkhCsfham1P6ruKF?usp=sharing
