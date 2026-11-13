# Use of AI in DeltaSAR · বন্যা সাথী

Team Astro Bengalis · NASA Space Apps Challenge 2026 · *Dancing with the SARs*

NASA's rule for AI-generated content: a valid reason for using it, the prompts explained, where the team's own work went, and every generating tool named. This file does that. Lines marked **[team: confirm]** must be checked by the team before submission.

## 1. Summary (paste into the project page "Use of AI" field)

> We used AI as a coding and drafting assistant, and in two clearly labelled features of the app. **Claude Code (Anthropic)** helped write and refactor our code (the NISAR radar processing kit, the alert system, the web app), its tests and deployment scripts, working from the plans, alert rules, data choices and screen designs our team wrote; we reviewed and tested every part (128 automated tests plus 7 live-data tests, a source audit that recomputes every headline number from its file, and checks of the live site). Inside the app, **Google Gemini** answers visitors' questions only from our published facts, with an automatic check that every number it states traces to our data, and **Gemini text-to-speech** reads approved Bangla alert text aloud on devices without a Bangla voice. No AI computes any number, decides, approves or sends an alert: thresholds, rules and approvals are fixed code and human decisions. No AI-generated images of people are used. Full log, prompts and checks: `docs/AI_USE.md` in our repository.

## 2. The rule we kept

**Fixed code computes; AI never computes.** Every value on the site comes from deterministic code in `backend/src/compute` and `backend/src/alerts` (water threshold from each scene's own histogram, change masks, bank-loss rule, three typed alert rules). A rule can only draft an alert; a person approves it. AI is not in the alert path.

## 3. AI tools, why, and what they produced

| Tool (model) | When | Valid reason | What it produced | Our own work and checks |
|---|---|---|---|---|
| **Claude Code**, Anthropic (Claude models; Claude Opus 5.5 on 13 Nov) | 11–13 Nov 2026 | A six-person team with 26 hours: speed up writing code we had specified | Science kit code (NISAR HDF5 subsetting, water and bank-loss rules, exposure, forecast baseline and ML challenger); alert layer (rules, engine, life cycle, ledger, delivery); guided-demo sandboxes; web app (story, explorer, demo, phone app, console, methods); tests; deploy files; drafts of these docs | Problem, study area, data audit, thresholds policy, alert rules and ranges, screen designs, Bangla copy and all decisions are ours (section 5). We ran the tests, read the code, checked numbers against source files, and tested the app in browsers and on phones |
| **Google Gemini 3.5 Flash-Lite** (Gemini API) | In the app, at run time | Let judges and residents ask questions in English or Bangla | "Ask DeltaSAR" answers on the public pages | Answers only from `backend/src/api/ask_facts.md`, which we wrote from our files; a server check flags any number not in those facts and asks once for a correction; replies in the language of the question (Bangla or English); named on the Methods page ("How AI was used"); never in the resident app's alert screens or the volunteer console |
| **Google Gemini 3.8 Flash TTS** (voice "Kore") | In the app, at run time | Many phones and laptops have no Bangla voice; people who cannot read must hear the alert | Spoken Bangla audio of approved alert sentences | It only reads text our code produced and a volunteer approved; it writes nothing. Recorded clips by a team member replace it when present (`frontend/public/audio/`) |
| Canva AI | Before the event (planning deck) | First draft of the plan slides | Slide layout ideas | We rejected AI photos of people, colour misuse and empty boxes, and rebuilt the deck ourselves (Plan A deck, slide 28) |
| Claude skills: UI/UX Pro Max, frontend-design, dataviz | Before and during the event | Checklists for touch targets, contrast and chart colours | Design checks | We kept 44–48 px targets, a tap alternative to swipe, status never by colour alone; rejected generic looks (Plan A deck, slide 28) |
| Adobe type-palette suggestions | Before the event | Font pairing ideas | Suggestions | None supported Bangla; we kept Baloo Da 2 and Hind Siliguri |
| OpenAI Codex **[team: confirm]** | Early Nov, research package | Assembling the research package (`.codex-finalizer` folder) | Packaging of research notes | Research and sources were gathered and checked by the team |

Not used: AI image generators for people or places; AI-generated data; AI voices presented as a real person.

## 4. Prompts (fair summary)

Coding assistant, in the order the work happened:

1. 11 Nov: "build the SAR + DEM kit from our data audit and build guide" → science kit.
2. 12 Nov: "make the complete plan", "start building according to the plan", "it should also contain phone view and web view" → first alert layer and app.
3. 13 Nov (this repository): "make a complete new plan, relevant to the existing one but most useful and impactful, then execute it", "host it with Render, Supabase and Vercel", "use NASA's APIs", "laptop should show expanded professional views, phone one view; make it coherent", "enhance the UI and colours", "it should tell in Bangla also; integrate the Gemini free API for a live chatbot", "did you follow the build guide", "does it need location access", "recheck with a full professional build with the sources", "do the deployment".

Run-time system instruction for the assistant (abridged): *answer only from the FACTS; never invent or change a number, date or place, and name the source of each number; you are not a warning service: never forecast floods or tell people to evacuate, and give 999 / FFWC / BMD / 1090 for danger; reply in Bangla or English; at most 120 words.* Full text: `backend/src/api/ask_routes.py`.

## 5. Where our own creative work went

- **The problem and the place:** the Jamuna's Sirajganj–Kazipur reach, families on the chars, people who share basic phones and may not read.
- **Research and data audit:** NISAR granule inventory, tracks 069A and 019D, the radar gap, FFWC danger levels, IMERG access, the build-guide and judging analysis (folders `NASA ISRO SAR and INFOs 1–5`).
- **Science choices:** threshold from each scene's own histogram and ±1 dB ranges; bank loss only when a later pass confirms it; never mixing tracks; the persistence test that showed our ML model does not beat the last picture, after which we removed every forecast claim.
- **Alert design:** three typed rules with ranges, volunteer approval, hold-to-reply, retries, call-backs, the append-only ledger, calm wording, "not an official warning" on every alert.
- **Accessibility and UX:** the twelve screen designs (`design/mockups_v2`), shape + word + colour status, Listen on every screen, large text, vibration and light.
- **Bangla:** the copy sheet and the native-reader review (`docs/BANGLA_REVIEW.md`).
- **Rejecting AI suggestions:** body-depth icons and "shelter: 15 minutes" were removed because the data cannot support them.
- **The pitch and videos.**

## 6. How AI output was checked

- 128 automated backend tests, run on SQLite, on PostgreSQL 18 and on the real Supabase database.
- 7 live-data tests against NASA CMR, ASF, GIBS, EONET, POWER, IMERG (SERVIR ClimateSERV) and FFWC: all pass; GitHub runs them daily.
- `scripts/audit_numbers.py` recomputes 23 headline numbers from their source files on every push; it caught two wording slips, which we fixed.
- The guided demo, run end to end in Chrome on the live site and again with all internet blocked (wifi-off rule).
- The assistant's number check caught Gemini writing "১০৯৯" instead of "১০৯০" (the helpline) in a Bangla answer; we added the correction round and the exact Bangla safety line to the facts.

## 7. Sign-off **[team: fill in]**

| Part | Reviewed by |
|---|---|
| Science numbers and method | |
| Alert rules and wording | |
| Web app on two Android phones | |
| Bangla text (native reader) | |
| This file | |
