# DeltaSAR · বন্যা সাথী: final build plan (v3)

**Written:** Fri 13 Nov 2026, 09:40 Dhaka (hour 2.7 of the event). **Replaces:** the "how to build" parts of `00_COMPLETE_PLAN.md` and `02_BUILD_SPEC.md`. The science, the rules, the words to use and the judging map in those files still stand.

## 1. What changed and why

The 12 Nov build (`deltasar/`) works: the alert rules, ledger and tests are solid. It is not a strong submission for three reasons:

| Problem | Effect on judging | Fix in v3 |
|---|---|---|
| A judge cannot experience the loop alone. It needs a console token, five manual clicks in the right order and a second device. | A global judge opening the link sees a Bangla phone screen and stops there. | **Guided demo (`/demo`)**: a private sandbox per visitor, a console and a phone side by side, six steps, one button each. A QR code lets a judge put their own phone into the sandbox. |
| No story. The analyst map is a dense tool page in English; the phone app is Bangla only. | "Could a global audience understand and remember this in 240 seconds?" scores low. | **Story page (`/`)**: why radar, the season, the bank that moved, what drives it, the loop, the limits. Every number links to its source file. |
| NASA data looks stale (radar 27 days old) and the newest work by the science teammate (13 Nov kit: insights, 12 water maps, retreat per site) is not in it. | Relevance and validity look weaker than they are. | **Live NASA strip**: the newest NISAR pass is read from NASA CMR in the browser (9 Nov, VALIDATED, published 12 Nov), the picture comes from NASA GIBS. The 13 Nov kit outputs replace the 12 Nov ones. |

## 2. The product: one URL, five doors

| Route | For | What it does | Data |
|---|---|---|---|
| `/` Story | Everyone, judges first | Scroll story in English with Bangla lines: cloud vs radar, 12 passes animated with the radar gap hatched, 187–232 ha of bank lost (confirmed), 712 buildings within 100 m of a retreating bank, drivers chart, skill table, HH vs HV, the alert loop, limits. Live strip from NASA CMR and EONET. | Static JSON on the CDN + NASA APIs called from the browser |
| `/explore` | Union officers, analysts, judges | Full map: pass timeline, swipe before/after, water per pass, new water, bank-loss sites, "times under water", unions ranked, NASA GIBS live layers (NISAR, OPERA DSWx, IMERG, MODIS flood, Sentinel-1). Click any point for a report. | Static + backend `/api/v1/point` |
| `/demo` | Judges (and the live pitch) | Sandbox replay of the real 24 Jul 2026 pass: rule drafts → volunteer approves → phone buzzes and speaks Bangla → "need help" → call-back → ledger and impact. Then the radar gap and the 75.2 mm rain day that correctly stayed silent. | Backend sandbox API + Supabase |
| `/app` | Residents (Bangla, voice first) | The installable phone app: start modes, join, home status, alert with hold-to-reply, evidence, map, rain, my alerts, simulated call. | Backend phone API |
| `/console` | Union volunteers (team at the event) | LIVE and REPLAY clock, drafts with receipts and input checks, approve/reject, help queue, ledger, impact. Token protected. | Backend console API |
| `/methods` | Judges checking validity | Method, thresholds, validation tables, every data source with licence, limits, AI use. | Static |

## 3. Architecture and hosting

```
                Browser (judge, resident, volunteer)
                 │                 │                        │
     static app + data (CDN)   NASA APIs, no key       /api/v1/*  (rules, people, alerts, ledger)
                 │            CMR · GIBS · EONET · POWER          │
            ┌────▼────┐                                     ┌─────▼──────┐        ┌──────────────┐
            │ Vercel  │                                     │  Render    │◄──────►│  Supabase    │
            │ React   │                                     │  FastAPI   │  SQL   │  Postgres    │
            │ PWA     │                                     │  (Docker)  │        │  (ledger,    │
            └─────────┘                                     │  + rasters │        │   people…)   │
                                                            └────────────┘        └──────────────┘
```

**Answer to "Render + Supabase + Vercel, will it work?" Yes, and it is the right split**, with four conditions:

1. **Render free tier sleeps after 15 minutes idle; the first request then takes 30–60 s.** The front end never waits on it: the story, explorer and evidence pictures are static on Vercel. For the judging window either (a) upgrade the one service to Render Starter (USD 7/month, no sleep) or (b) keep it warm with a 10-minute ping (UptimeRobot or cron-job.org, free). The app also shows "waking the server" instead of a blank screen.
2. **Render's disk is wiped on every deploy**, so the database must be Supabase, not SQLite. Use the *Session pooler* connection string (IPv4) with `?sslmode=require`.
3. **Supabase free projects pause after 7 days without traffic.** Fine for the event; un-pause from the dashboard afterwards.
4. **Web Push needs HTTPS**: both Vercel and Render give it. iPhone needs "Add to Home Screen" first; demo phones should be Android with Chrome.

Not needed: Redis, PostGIS, a job queue, object storage. The radar rule samples small pre-computed rasters (40 m, about 60 MB in all) baked into the Docker image.

## 4. NASA data: what is used and how

| Source | Access | Key? | Where it appears |
|---|---|---|---|
| NISAR L2 GCOV (ASF DAAC) | Processed by the kit from Earthdata (login) | Earthdata Login, for processing only | All water maps, bank loss, radar rule |
| NASA CMR search | Browser, live | No | Newest NISAR pass, publication delay, OPERA file count |
| NASA GIBS WMTS | Browser tiles, live | No | NISAR picture for any pass incl. 9 Nov, OPERA DSWx-S1, IMERG, MODIS flood, Sentinel-1 RTC |
| NASA EONET | Browser, live | No | Flood events in Bangladesh 2026 (8 Jul, 9 Sep) marked on the season timeline |
| NASA POWER | Browser, live | No | Rain at the clicked point (Explorer report) |
| GPM IMERG via NASA SERVIR ClimateSERV | Backend job, cached | No | Rain rule and rain screen |
| OPERA DSWx-S1 | GIBS layer; CMR count | No | Independent water map shown beside ours |

**api.nasa.gov key: not needed.** None of the APIs above use it. Register one anyway (free) and set `NASA_API_KEY` only if a later feature uses an api.nasa.gov endpoint. Earthdata Login matters only for re-running the pipeline on a new pass.

## 5. Build order (this session, then the team)

| # | Work | Owner | Done when |
|---|---|---|---|
| B1 | New repo `deltasar-app/`: 13 Nov kit + 12 Nov alert layer + tests; one Python 3.13 env | Claude | `pytest` passes |
| B2 | Backend: sandbox scope (own clock and people per visitor), `/sandbox/*` routes, `/point` report, CORS for Vercel, Postgres-ready, Dockerfile, `render.yaml` | Claude | Guided loop runs end to end through the API in a test |
| B3 | Data jobs: `build_backend_data` (40 m rasters + JSON for the image), `build_web_data` (WebP overlays ≤ 2048 px, story JSON, validation, drivers) | Claude | Web data under 60 MB; backend data under 80 MB |
| B4 | Front end: design system, Story, Explore, Demo, phone app, Console, Methods; PWA and push | Claude | `tsc` clean, production build, checked in a real browser at phone and laptop width |
| B5 | Deploy docs and env templates; Supabase setup; keep-warm | Claude, then Lead | `docs/DEPLOY.md` steps work from a fresh account |
| T1 | Ingest the 9 Nov VALIDATED pass (`src/pipeline/ingest_new.py` with `NISAR_L2_GCOV_V1`), run S2 check, rebuild data | Pipeline (Ehsan) | `radar_rule/index.json` lists 9 Nov; rerun `jobs.build_*` |
| T2 | Native read of all Bangla text; record the five voice clips into `frontend/public/audio/` | Story (Muaza) | Clips play on the phone |
| T3 | Deploy with team accounts (Vercel, Render, Supabase), VAPID keys, test on two Android phones | Lead (Saifullah) + Alerts (Sanaullah) | Approve in `/console` makes both phones buzz |
| T4 | User test with 3–5 people outside the team on `/demo` and `/app` | Story + Web (Tahjir) | Counts written in `docs/USER_TEST.md` |
| T5 | Video 2 (240 s) from `/` and `/demo` screen recordings, by 18:30 | Story + Lead | Uploaded |

## 6. Demo script (3 minutes, uses `/demo`)

| Time | Screen | Say |
|---|---|---|
| 0:00 | `/` hero, then swipe cloud vs radar | "Monsoon cloud hides the Jamuna from ordinary satellites. NISAR's L-band radar sees through it." |
| 0:25 | `/` season strip, play | "Twelve passes this season. The gap from 27 July to 10 August stays a gap: we never fill it." |
| 0:45 | `/` bank-loss section | "187 to 232 hectares of mainland became river, confirmed by a later pass. 712 buildings now stand within 100 m of a bank that retreated." |
| 1:05 | `/demo` step 1–2 | "Replay of 27 July. NASA publishes the 24 July pass; a fixed rule checks every home and drafts an alert. It cannot send." |
| 1:35 | step 3 | Approve. The phone buzzes and speaks Bangla. A judge's own phone, if scanned, buzzes too. |
| 2:00 | step 4–5 | Hold "need help". The call-back appears in red; the ledger counts it. |
| 2:20 | step 6 | "During the radar gap the app says 'no new radar'. On 5 August the wettest spot had 75.2 mm; the line was 76; the rule stayed silent, as written." |
| 2:40 | `/methods` limits | "Radar arrives about two days after each pass. The last picture beats our forecast model, so we show the picture. Not an official warning: FFWC, BMD, 1090." |

## 7. What we never cut

Listen button · data age on every screen · receipts · the visible radar gap · PROVISIONAL / VALIDATED label · volunteer approval · "not an official warning".

## 8. Status at 13 Nov, about 11:00 (built in this session)

- B1–B5 done. Backend: 121 tests pass on SQLite and on PostgreSQL 18 (same engine as Supabase). Front end: type-checked, production build, the guided demo run end to end in Chrome on the production build; no horizontal scroll at phone or laptop width.
- **Laptop vs phone.** Every page is laptop-first and collapses for phones. `/app` on a phone is the full-screen app; on a laptop it is the same app beside an expanded view (large map, radar, river and rain in detail, alert history). `/demo` on a phone shows the steps, then the phone, then the console.
- **Challenge Resources tab (published 13 Nov)** checked: Earthdata Search, ASF Vertex, NISAR Data User Guide, Intro to SAR, ARSET, NISAR StoryMaps and white papers, UAVSAR; partners CSA (RADARSAT-1, RCM, SAR Python tutorial) and CONAE (SAOCOM, L-band). Nothing changes the plan: we already use ASF/Earthdata NISAR GCOV. Each pass now links to its NASA CMR record and to ASF Vertex; `/methods` lists every resource and how it was used; SAOCOM and RCM are named as next steps. The story page answers each line of the challenge's Objectives, quoting it.
- Still for the team: T1 (ingest the 9 Nov VALIDATED pass), T2 (native check of Bangla lines marked NEW; record voice clips), T3 (deploy with team accounts, `docs/DEPLOY.md`), T4 (user test), T5 (videos).
