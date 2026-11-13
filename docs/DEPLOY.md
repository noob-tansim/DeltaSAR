# Deploy: Supabase + Render + Vercel

About 30 minutes with three free accounts. Order matters: database first, then the API, then the web app.

| Piece | Service | Free tier caveat | Fix |
|---|---|---|---|
| Database (people, alerts, ledger) | **Supabase** Postgres | Pauses after 7 days without traffic | Un-pause in the dashboard after the event |
| API (`backend/`) | **Render** web service, Docker | Sleeps after 15 min idle; first request then takes 30–60 s. Disk is wiped on every deploy (so no SQLite) | For the judging window: upgrade to *Starter* (no sleep), or ping `/api/v1/health` every 10 min (UptimeRobot / cron-job.org). The web app also shows “waking the server”. |
| Web app (`frontend/`) | **Vercel** | Hobby plan is for non-commercial use | Fine for the hackathon |

Region: put Supabase and Render both in **Singapore** (closest to Bangladesh).

## 1. Supabase (database)

1. New project → name `deltasar`, region *Southeast Asia (Singapore)*, set a strong database password.
2. Project → **Connect** → *Session pooler* (IPv4). Copy the URI, e.g.
   `postgresql://postgres.<ref>:<password>@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres`
   and append `?sslmode=require`.
   Use the **session** pooler (port 5432), not the transaction pooler (6543).
3. Nothing else: the API creates its tables on first start.

## 2. Render (API)

1. Push this repository to GitHub (public, for the judges).
2. Render → **New → Blueprint** → pick the repository. It reads `render.yaml` (one Docker web service, root `backend/`).
3. Fill the variables marked *sync: false*:
   * `DATABASE_URL` — the Supabase URI from step 1.
   * `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` — run `python -m jobs.make_vapid_keys` locally (optional; without them alerts still appear while the app is open).
   * `GEMINI_API_KEY` — optional, for the "Ask DeltaSAR" assistant. Free key at https://aistudio.google.com → *Get API key*. Without it the assistant's built-in FAQ still works. Note: on Google's free tier, prompts may be used to improve Google's products, so the widget tells visitors not to type personal details.
4. After the first deploy, check `https://<service>.onrender.com/api/v1/health` → `"ok": true`, `"database": "postgres"`, 12 radar passes.
5. Copy `CONSOLE_TOKEN` (generated) from the Render dashboard for the volunteer console.

## 3. Vercel (web app)

1. Vercel → **Add New → Project** → import the repository. **Root Directory: `frontend`** (framework Vite is detected; `vercel.json` sets the rest).
2. Environment variables (Production and Preview):
   * `VITE_API_BASE` = `https://<service>.onrender.com` (no trailing slash)
   * `VITE_REPO_URL` = the GitHub URL
3. Deploy. If the Vercel domain is not `deltasar.vercel.app`, set Render's `ALLOWED_ORIGINS`, `PUBLIC_BASE_URL` (and, if needed, `ALLOWED_ORIGIN_REGEX`) to the real domain and redeploy the API.

## 4. Check it

```bash
cd backend
python scripts/smoke_deployed.py --api https://<service>.onrender.com --web https://<your-app>.vercel.app
```

It runs the guided demo through the public API, checks the database is Postgres, CORS, the assistant, and that the web app serves its pages and data. All lines should say PASS.

## 5. Before judging

- [ ] Open `/api/v1/health` 10 minutes before (or keep the ping running).
- [ ] Run `/demo` once end to end on the hosted site; scan the QR code with an Android phone and allow notifications.
- [ ] Open `/app` on the two demo phones, join, *Add to Home screen*.
- [ ] Test the repository link from a phone that is not logged in.

## 6. Backup: laptop + tunnel

If hosting fails or the venue network blocks it: run both locally (README) and expose the Vite server with an HTTPS tunnel. Web Push and service workers need HTTPS.

## Updating the data after a new NISAR pass

```bash
cd backend
python -m src.pipeline.ingest_new                 # full kit environment, Earthdata Login
python -m jobs.j1_radar_rule_layers
python -m jobs.build_backend_data --science outputs/kazipur --radar-rule outputs/kazipur/radar_rule --unions cache/vector/unions.geojson
python -m jobs.build_web_data     --science outputs/kazipur --radar-rule outputs/kazipur/radar_rule --unions cache/vector/unions.geojson
git commit -am "data: NISAR pass <date>" && git push   # Render and Vercel redeploy by themselves
```
