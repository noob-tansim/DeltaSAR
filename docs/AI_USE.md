# How AI was used

The participants guide asks for each AI tool: what it was asked, what it produced, and what a person checked.

**Rule we kept:** AI writes code and drafts text. It computes no number shown on any screen and is not in the alert path. Numbers come from fixed code (`backend/src/compute`, `backend/src/alerts/rules.py`); alerts are sent only after a person approves them.

| Tool | Asked to | Produced | Checked by a person (fill in names) |
|---|---|---|---|
| AI coding assistant (Claude Code), 11–12 Nov | Write the SAR + DEM kit and the first alert layer from the team's build spec | `src/acquire`, `src/compute`, `src/pipeline`, `src/alerts`, tests | Thresholds and results checked against the kit's own receipts; see `docs/AI_USE_kit.md` |
| AI coding assistant (Claude Code), 13 Nov | Combine kit and alert layer, add sandboxes and deploy files, build the web app from the team's plan, mock-ups and design tokens | `backend/src/alerts/sandbox.py`, `backend/src/api/app.py`, `backend/jobs/build_*`, `frontend/` | (fill in) |
| AI assistants for research, early Nov | Find sources, draft plans and Bangla copy | Research notes, plans, draft Bangla sentences | Bangla lines marked `NEW` in `frontend/src/phone/strings.ts` still need a native reader |

What a person must still check before submission:

- Every Bangla sentence (native reader).
- Every number quoted in the pitch against the files named in the README table.
- The demo run on the hosted site, on two real Android phones.

## AI inside the product: the "Ask DeltaSAR" assistant

The public pages have an optional assistant that uses **Google Gemini** (free API tier, key on the server only).

- It answers only from `backend/src/api/ask_facts.md`; every number there comes from the project's files.
- After each answer, the server checks that every number in it appears in those facts (`untraced_numbers`); the widget shows a warning when one does not. This follows the build guide's rule that every number a model states must trace to a source.
- It is not in the alert path: it cannot draft, approve or send anything, it never gives warnings, and it is not shown in the resident app or the volunteer console.
- Six common questions are answered from a fixed bilingual FAQ (no AI). Without `GEMINI_API_KEY` only the FAQ works.
