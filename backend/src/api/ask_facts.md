# FACTS for "Ask DeltaSAR" (the only knowledge the assistant may use)

## The project
- DeltaSAR · বন্যা সাথী (Bonna Sathi) by Team Astro Bengalis, Bangladesh. NASA Space Apps Challenge 2026, challenge "Dancing with the SARs". Code is open source (Apache-2.0).
- DeltaSAR turns each NISAR radar pass over the Jamuna river into maps of where water and riverbank changed, with a receipt (source file, granule id, threshold, date) for every number.
- বন্যা সাথী is the resident app: Bangla first, every screen can be read aloud, status shown as shape + word + colour. A union volunteer approves every alert before it is sent. People answer "I am safe" or "I need help" by pressing and holding a button (or 1 / 2 on a phone call, simulated in the demo). Every step is written to an append-only ledger; impact numbers are counted only from the ledger.
- Pages: Story (/), Explorer map (/explore), guided live demo (/demo), the resident app (/app), Methods and data (/methods), volunteer console (/console, team only).

## Study area
- The Sirajganj–Kazipur reach of the Jamuna (Brahmaputra) river in Bangladesh, about 45 × 65 km (bounding box 89.46–89.918 E, 24.205–24.80 N), on a 20 m analysis grid. 145 unions (smallest rural administrative units) are covered, in upazilas such as Kazipur, Sirajganj Sadar, Belkuchi, Chauhali, Dhunat, Sariakandi, Bhuapur, Gopalpur.
- Chars are river islands of sand and silt; families living there lose farmland when the river moves.

## NISAR data
- NISAR is the NASA–ISRO Synthetic Aperture Radar satellite. It uses L-band radar (about 24 cm wavelength), which passes through cloud and rain, day and night.
- Product used: NISAR L2 GCOV (geocoded polarimetric covariance), distributed by NASA's ASF DAAC (Alaska Satellite Facility). Data before 25 Oct 2026 is PROVISIONAL (CRID P05023); VALIDATED files (CRID P05036) exist from 25 Oct 2026.
- Two tracks cover the whole reach: 069A (ascending, about 05:21 Dhaka time) and 019D (descending). Each track repeats every 12 days. Different tracks are never mixed in one comparison.
- 13 passes were processed: track 069A on 18 Jun, 30 Jun, 12 Jul, 24 Jul, 17 Aug, 29 Aug, 10 Sep, 22 Sep, 4 Oct, 16 Oct and 9 Nov 2026 and track 019D on 27 Jun and 13 Oct 2026 (UTC dates).
- The 9 Nov 2026 pass (track 069A) is a VALIDATED NISAR file (CRID P05036; the earlier ones are PROVISIONAL, CRID P05023). It was streamed from NASA's ASF archive with Earthdata Login and added only after a consistency check: median radar brightness (HH) over the core river was -18.24 dB and over stable land -7.94 dB, both inside the range of the ten earlier track-069A passes (river -18.99 to -17.10 dB, land -8.83 to -7.29 dB).
- On 9 Nov 2026: 292.2 km² of open water in the reach, 128.1 km² of it outside the main channel (16 Oct: 317.6 and 148.0 km²); modelled river flow 5,727 m³/s (GloFAS). New water compared with 18 Jun: 24.19 km² at the threshold, 20.09 to 49.88 km² over the ±1 dB range.
- Not yet processed: the track 019D passes of 25 Oct and 6 Nov 2026 (VALIDATED files at NASA). The newest pass, 9 Nov 2026 on track 069A, is processed.
- The radar was off from 27 July to 10 August 2026. That gap is shown as a gap and never filled by a model.
- NASA published track 069A files 45 to 71 hours after the satellite passed (measured from NASA CMR records since late July), except 122 hours for 17 Aug, the first pass after the radar gap.

## Method
- Open water is dark in radar because smooth water reflects the signal away. Water = HH backscatter below a threshold found from each track's own baseline scene histogram: −15.62 dB for track 069A (valley between water mode −18.12 dB and land mode −10.38 dB); −14.06 dB for track 019D (midpoint method, cross-check only). A 3×3 median filter is applied first. Every area is also computed at the threshold −1 dB and +1 dB, and reported as a range.
- New water = water at a pass that was land at the baseline pass of the same track (069A baseline: 18 Jun 2026).
- Mainland riverbank loss (the only thing called erosion) = mainland land that became water connected to the main channel, touching the old bank line, within 1,500 m of it; confirmed only when a later pass of the same track still shows water.
- Flooded vegetation (HH > −8 dB, HH−HV > 6 dB, HH rose ≥ 3 dB) is experimental; in October it mostly picks up flooded aman rice.

## Results
- Mainland riverbank lost between 18 Jun and 4 Oct 2026, confirmed by the 16 Oct pass: 187 to 232 hectares, in 38 sites of 0.5 ha or more. About 74 ha of it was cropland (ESA WorldCover 2021) and 47 buildings stood on it (Google Open Buildings, older imagery; not a damage count).
- Largest single site: S01 in Char Girish union, Kazipur upazila, 38.8 ha, the bank moved up to 228 m. Char Girish lost the most mainland bank: 41 ha in 4 sites.
- 712 buildings and 242 ha of cropland stand within 100 m of a bank that retreated this season (bank line of 16 Oct 2026); 305 buildings within 50 m.
- Bank, not flood: on 4 Oct the river carried about 16,180 m³/s, less than 27,605 m³/s on 18 Jun (GloFAS model flow), so the change is the bank moving, not higher water.
- Peak flooding: the 24 Jul pass saw about 776 km² of water in the reach (596 km² beyond the permanent channel). Flooded cropland peaked at 39,425 ha on 24 Jul. 7,296 ha of cropland was under water on 6 or more of the 10 track-069A passes.
- Physical drivers: water extent follows upstream river flow more than local rain (about 5.8 km² more water per extra 1,000 m³/s, R² 0.21, weak because rising and falling rivers differ). A model using local rain alone showed no skill on any pass.
- Polarisation: HH separates water from land best: water–land contrast is 9.0–11.6 dB in HH but only 6.8–8.2 dB in HV. The reason: in HV (not HH), water is so dark that it sits near the sensor's noise floor (about −23 dB), so HV cannot separate it as well.
- Forecast skill (mean CSI over 9 passes, each predicted without seeing it): river-flow rule 0.17, machine-learning model 0.48, "same as the last radar pass" 0.50. Persistence wins on 6 of 9 passes. So the app shows the newest picture and its age, never a forecast as fact.
- Wettest day of the season in the reach by NASA IMERG: 75.2 mm on 5 Aug 2026; the default rain alert level is 76 mm (3 inches), so the rain rule correctly stayed silent.

## Alert rules (fixed code, no AI)
- Radar rule: new water within the person's distance from home (default 1 km; range 0.2–5 km). "Sure" only if the stricter threshold (T−1 dB) also puts water inside that distance. No alert from a radar picture older than 14 days.
- River rule: FFWC level (observed, or forecast up to 3 days ahead) at or above danger level − 0.30 m. Danger levels: Kazipur 14.80 m, Sirajganj 12.90 m.
- Rain rule: 24-hour rain at or above the person's own level (76 mm = 3 in, 152 mm = 6 in, or custom 10–300 mm).
- A rule only drafts. A volunteer must approve within 15 minutes or the draft turns red and never sends itself. Unanswered alerts are retried twice. "Help" opens a call-back task.

## Data sources
- NASA: NISAR (via ASF DAAC and NASA CMR/Earthdata Search), NASA GIBS map tiles (NISAR, OPERA DSWx-S1 water, Sentinel-1 RTC, MODIS, IMERG), NASA EONET flood events, NASA POWER rain, GPM IMERG rain via NASA SERVIR ClimateSERV. No api.nasa.gov key is needed.
- Others: FFWC (Bangladesh Water Development Board) river levels; GloFAS via Open-Meteo (river flow model); Copernicus DEM and Sentinel; MERIT Hydro; JRC Global Surface Water; ESA WorldCover; Google Open Buildings; geoBoundaries.

## Limits
- Not real-time (radar about two days after each pass), not a forecast, not water depth, not an official warning.
- In the demo, voice calls and SMS are simulated and labelled; all people are demo participants at real union centre points.
- Bangla text is a draft awaiting a native reader's check.

## Safety
- This is not an official warning. Official flood forecasts: FFWC and BMD. Call 1090 (free) for the government's voice forecast. In an emergency call 999.
- In Bangla, exactly: "এটি সরকারি সতর্কবার্তা নয়। সরকারি পূর্বাভাস: FFWC ও BMD; বিনা খরচে ১০৯০ নম্বরে ফোন করুন। জরুরি প্রয়োজনে ৯৯৯।" The numbers are 1090 (১০৯০) and 999 (৯৯৯), never anything else.
