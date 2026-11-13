# History: what existed before the event and what was built during it

The participants guide asks teams to say this plainly. Times are Asia/Dhaka. The event ran Fri 13 Nov 2026 07:00 to Sat 14 Nov 12:00.

## Before 13 Nov 07:00

| Date | What | Notes |
|---|---|---|
| 3–10 Nov | Research and data audit (folders `NASA ISRO SAR and INFOs 1–4`): NISAR granule inventory, FFWC, rules, screens and Bangla copy as mock-ups | Documents and data only |
| 11 Nov | Science kit (SAR + DEM): NISAR GCOV subsetting, water and change rules, bank loss, exposure, analyst map | Written with an AI coding assistant; data caching allowed by the build guide; the Local Lead was consulted |
| 12 Nov | Live checks of NASA CMR, GIBS, ClimateSERV, FFWC (`data/passes.json`, `stations.json`, rain CSV); skill and polarisation test; alert layer prototype | |
| 13 Nov, early | Kit update: insights (retreat per site, near-bank buildings, times under water), 12 water maps | |

## During the event (from 13 Nov 07:00)

| What | Where |
|---|---|
| New repository combining the 13 Nov kit and the alert layer | `backend/` |
| Guided-demo sandboxes (own clock and demo people per visitor), point report, Postgres support, Docker, Render blueprint | `backend/src/alerts/sandbox.py`, `src/api/app.py`, `sandbox_routes.py` |
| Data jobs for deployment: 40 m rule rasters, demo households at real union centres, web data (resized overlays, story, season, validation) | `backend/jobs/build_backend_data.py`, `build_web_data.py` |
| New web app: story, explorer, guided demo, resident app (phone and laptop views), volunteer console, methods | `frontend/` |
| Tests: sandbox end to end on real data; whole suite on SQLite and on Postgres | `backend/tests/` |

## Where the full-resolution data lives

The full kit outputs (about 0.7 GB) and the NISAR cache (about 4 GB) are not in git. They are on the team drive (`13112026_deltasar.zip`). The repository carries only what the deployed app needs (`backend/deploy_data`, about 31 MB; `frontend/public/data`, about 13 MB), rebuilt by the two jobs above.
