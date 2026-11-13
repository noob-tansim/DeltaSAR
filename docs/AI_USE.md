# Use of AI

DeltaSAR · বন্যা সাথী, by Team Astro Bengalis, NASA Space Apps Challenge 2026 (Dancing with the SARs).

**Short version for the project page:** We used Claude Code as a coding assistant, Google Gemini for the website's question box and for reading Bangla alerts aloud, and two tools for the video's sound and subtitles. AI never computes our numbers and never decides or sends an alert: that is fixed code and a human volunteer. The problem, the science choices, the alert design, the Bangla text and the video script are our own work.

## Tools we used

- **Claude Code (Anthropic):** helped write and refactor our code (radar processing, alert system, website), tests and deployment files, and helped edit our 240-second video.
- **Google Gemini:** answers visitors' questions in the "Ask DeltaSAR" box on the website.
- **Gemini text-to-speech:** reads an approved Bangla alert aloud when a phone has no Bangla voice.
- **Whisper (run on our laptop):** timed the video subtitles to our own voice-over.
- **Adobe Podcast Enhance Speech:** removed background noise from narration recorded at home.

## Why

We are six people with about 26 hours, so AI helped us write code we had already planned. In the app, the question box lets judges and residents ask in English or Bangla, and the voice helps people who cannot read.

## What the AI worked on

- Claude Code: our plans, data notes and code. The NISAR radar files are processed by our code, not by AI.
- Gemini question box: only a facts file we wrote (`backend/src/api/ask_facts.md`) and the visitor's question. A check flags any number that is not in our facts.
- Gemini voice: only alert text produced by our rules and approved by a volunteer.
- Whisper and Adobe: our own voice recordings.

## What the AI did not do

- It does not compute any number. Water maps, riverbank loss, exposure and the alert rules are fixed code in `backend/src/compute` and `backend/src/alerts`, which we tested.
- It does not decide or send alerts. A rule drafts an alert and a volunteer approves it.
- No AI images of people, no AI-made data, and no AI voice standing in for a team member.

## Prompts

Coding, in the order we worked:

- "Build the SAR + DEM kit from our data audit and the build guide."
- "Make the complete plan and start building. It should have a phone view and a web view."
- "Host it with Render, Supabase and Vercel. Use NASA's APIs."
- "Use Earthdata Login to process the newest NISAR pass."
- "The chatbot should answer in Bangla as well as English."
- "Make the 240-second video from our script and voice-over, using the live site's screens."

Question box instruction (short): answer only from the facts; never invent or change a number; this is not a warning service, so for danger give 999, FFWC, BMD and 1090; reply in the language of the question. Full text: `backend/src/api/ask_routes.py`.

## Our own work

- The problem and the place: the Jamuna at Sirajganj–Kazipur and the families on its river islands.
- The research: which NISAR passes cover the reach, the radar gap, FFWC danger levels and rain data.
- The science choices: a water threshold from each scene's own data with a ±1 dB range, riverbank loss only when a later pass confirms it, and dropping our forecast when it did not beat the latest picture.
- The alert design: three rules, volunteer approval, press-and-hold answers, and "not an official warning" on every alert.
- The screen designs, the Bangla text, the video script, the narration and the team introductions.
- The checking: we ran the tests, compared the numbers with their source files, and tried the site on laptops and phones.
