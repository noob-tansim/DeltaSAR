# AI use log

| Date | Tool | What it was used for | What a human checked/changed |
|------|------|----------------------|------------------------------|
| 2026-11-11 | Claude | Starter code structure, NISAR HDF5 cutter, flood-probability model draft | (fill in: what you tested and changed) |
| 2026-11-11 | Claude (coding assistant) | Bank-loss rules, exposure (land cover, buildings), dashboard redesign, auto-ingest, discharge-driven forecast, ML challenger code | (fill in) |
| 2026-11-12 | Claude (coding assistant, Claude Code) | Alert layer (`src/alerts/`, `src/api/alerts_routes.py`, `jobs/`), tests, phone app and volunteer console (`web/app/`), from the team's written plan and spec (`NASA ISRO SAR and INFOs 5/`). Prompts: "make the complete plan", "start building according to the plan", "it should also contain phone view ... and web view" | (fill in: what you ran, tested on real phones, and changed) |

## Which numbers come from what

No generative AI produces any number shown on the dashboard. A coding assistant wrote code; the code computes the numbers.

**Deterministic rules (same input -> same output, no training):**
- Water mask per radar pass: HH below a per-track threshold (histogram valley of the track's baseline scene), `src/compute/water.py`.
- Mainland bank loss, char change, new water: rule-based masks and connectivity tests, `src/compute/water.py`.
- Exposure: land cover (ESA WorldCover 2021) and building counts (Google Open Buildings v3 footprints, confidence >= 0.7) inside the bank-loss sites, `src/compute/exposure.py`.
- Baseline 30-day water forecast: "stage proxy" model, height above river <= h(discharge), with h(Q) fitted by isotonic regression on the radar passes, `src/compute/forecast.py`.
- Cloud masking of Sentinel-2 composites: fixed rules (SCL classes, QA60 bits, blue and NDSI thresholds), `src/acquire/gee_optical.py`.
- Old 7-day flood-likelihood layer (Advanced): logistic formula with physical priors, two parameters refitted per pass, `src/compute/flood_prob.py`.

**Trained statistical model (only one):**
- `src/compute/water_ml.py`: scikit-learn HistGradientBoostingClassifier, "is this pixel water on date d", trained on the NISAR water masks of past passes (features: height above river, distance to river, DEM, WorldCover class, GloFAS discharge and its 5/10-day means and trend, antecedent rain, previous-pass state). Fixed seed, validated leave-one-pass-out against the deterministic baseline. It is used for the PREDICTIVE layer only if it beats the baseline on most held-out passes; `forecast.json` -> `model_used` says which one is shown, and the dashboard labels it "statistical model trained on NISAR water masks". The fitted model and its receipt are in `cache/water_ml_<aoi>_<track>.joblib` / `_receipt.json`.

Observed numbers (bank loss, cropland, buildings) are always rule-based. Predictions cover water extent only, never bank erosion.

**Alert rules (added 12 Nov):** `src/alerts/rules.py` holds three fixed rules (radar, river, rain). They are plain comparisons against typed limits. No AI model decides whether an alert is drafted, approved or sent; a person approves every alert in the console. Alert sentences are fixed templates filled with numbers (`src/alerts/messages.py`).
