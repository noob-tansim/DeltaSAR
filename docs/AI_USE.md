# Use of AI in this project

## Tools

- Claude (Anthropic) via Claude Code — writing and refactoring code, tests and deployment files; editing our 240-second video.
- Google Gemini (3.5 Flash-Lite) via the Gemini API — the "Ask DeltaSAR" question box on the website (see `backend/src/api/ask_routes.py`).
- Gemini text-to-speech via the Gemini API — reads approved Bangla alerts aloud on phones with no Bangla voice (see `backend/src/api/tts_routes.py`).
- Whisper, run on our laptop — timed the video subtitles to our own voice-over.
- Adobe Podcast Enhance Speech — removed background noise from narration recorded at home.

## What the AI did

- Generated first drafts of the radar processing code, the alert system and the website, from our plans. We reviewed, changed and tested them.
- Answers visitors' questions at run time, only from a facts file we wrote (`backend/src/api/ask_facts.md`). A server check flags any number that is not in those facts.
- Reads alert text aloud at run time. The text comes from our rules and is approved by a volunteer.
- Helped assemble our video from our script, voice-over, team recordings and screens of the live site.

## What the AI did not do

- All numbers come from fixed code in `backend/src/compute` and `backend/src/alerts`, tested by the team. No AI computes a number, and no AI decides or sends an alert: a volunteer approves every alert.
- The problem, the study area, the dataset selection, the water and riverbank-loss method, the alert rules, the screen designs, the Bangla text and the video script are ours.
- No AI images of people, no AI-made data, and no AI voice standing in for a team member.

## Prompts

Full prompt text for the question box: `backend/src/api/ask_routes.py`. Main coding prompts, in order:

- "Build the SAR + DEM kit from our data audit and the build guide."
- "Make the complete plan and start building. It should have a phone view and a web view."
- "Host it with Render, Supabase and Vercel. Use NASA's APIs."
- "Use Earthdata Login to process the newest NISAR pass."
- "The chatbot should answer in Bangla as well as English."
- "Make the 240-second video from our script and voice-over, using the live site's screens."
