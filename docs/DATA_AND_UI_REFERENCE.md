# DeltaSAR technical and UI documentation

**Audience:** analyst, developer, or UI designer consuming the DeltaSAR files/API.  
**Scope snapshot:** code and file layout inspected 13 November 2026.  
**Project:** Sirajganj–Kazipur reach of the Jamuna, Bangladesh.

This is the UI implementer's source of truth for interpreting generated data. Existing operational notes remain useful: [README](../README.md), [handoff/run guide](HANDOFF.md), [offline dry run](OFFLINE_DRYRUN.md), and [AI use log](AI_USE.md). When this document and code disagree, use the current implementation and update this document.

## 1. What the system does

DeltaSAR is a geospatial analysis pipeline plus a MapLibre browser UI and a FastAPI read API. It takes NISAR L-band radar observations, classifies open water, compares same-track observations, derives candidate mainland bank loss and exposure, and can generate experimental water forecasts. Numbers are computed by explicit code and rules; the UI should not invent or recompute them.

There are two product types:

- **Observed:** per-pass water masks and before/after change from NISAR. Bank loss, char change, exposure and location context are observations or deterministic derivations.
- **Predictive:** experimental future water extent. It is not an official flood warning and does not predict erosion.

The configured AOI is `kazipur`, labelled `Sirajganj-Kazipur reach (Jamuna)`. Internal analysis uses UTM 45N (EPSG:32645), 20 m pixels, extent `[750000,2680000,795000,2745000]` metres. Public geometry and API coordinates use WGS84 longitude/latitude. Approximate AOI bbox is `[89.46,24.205,89.918,24.80]` in `[west,south,east,north]` order.

Only tracks `069A` (ascending) and `019D` (descending) cover the full AOI. **Never compare dates from different tracks.** Track thresholds and viewing geometry differ. A permanent instrument gap from 27 July through 10 August 2026 is represented as missing data, not interpolated.

## 2. Architecture and run flow

```text
External sources / local NISAR HDF5
       ↓ acquire: subset, terrain, optical, weather, vector inputs
cache/ (source rasters, receipts, API responses, calibration state)
       ↓ src.pipeline.run_aoi
outputs/kazipur/ (JSON contracts, GeoJSON, point-query rasters, map overlays)
       ↓ src.api.main (FastAPI) + web/index.html (MapLibre UI)
```

Important modules:

| Path | Purpose |
|---|---|
| `src/config.py` | AOI/grid, supported tracks, preset dates, constants, cache/output roots |
| `src/acquire/nisar_subset.py` | Read NISAR GCOV HDF5, cut AOI, convert linear backscatter to dB, write GeoTIFFs and receipts |
| `src/acquire/gee_layers.py` | Earth Engine river, HAND, DEM and optical base layers |
| `src/acquire/terrain_fallback.py` | Local fallback river mask and approximate height above river when GEE terrain is unavailable |
| `src/acquire/gee_optical.py`, `gee_scene.py` | Sentinel-2 pixel composites or selected Sentinel-2 / Landsat 8/9 whole scenes around radar dates |
| `src/acquire/buildings.py`, `unions.py`, `gunw_coherence.py` | Building footprints, administrative boundaries, optional InSAR coherence |
| `src/acquire/weather.py`, `safe.py` | Open-Meteo/NASA POWER weather and live→cache→fixture fallback |
| `src/compute/water.py` | Threshold, per-date water masks, change classes, bank-loss rules and area ranges |
| `src/compute/exposure.py` | Site polygons, land-cover/building/union context, banklines and chips |
| `src/compute/forecast.py` | Discharge vs height-above-river baseline forecast, validation, timeline |
| `src/compute/water_ml.py` | Optional trained classifier challenger for future water only |
| `src/compute/flood_prob.py` | Older experimental 7-day probability layer with per-pass calibration |
| `src/compute/compare.py` | Same-track custom date comparison; adds stage warning from discharge |
| `src/pipeline/run_aoi.py` | Main deterministic processing and static output generation |
| `src/pipeline/ingest_new.py` | Discover/cut new radar observations and refresh results |
| `src/pipeline/publish.py` | Build into a staging directory and atomically swap outputs |
| `src/api/main.py` | Read API and static file serving |
| `web/index.html` | UI, map layers, timeline, compare, point lookup and charts/cards |
| `scripts/make_synthetic_demo.py` | Artificial training/demo fixture generator; its values are not real observations |

`src.config.OUTPUTS` defaults to `outputs/`; `DELTASAR_OUTPUTS` can point the server/build at another output root (the handoff uses `demo_fixtures/outputs`). `cache/`, `outputs/` and `.env` are local/ignored. `demo_fixtures/` contains portable sample outputs/API responses. `outputs_prev/` is an archived generated snapshot. `dist/` contains packaged/built artifacts; generated rasters and PNGs are not independent sources of truth.

## 3. Data provenance: where the inputs come from

| Input | Source / retrieval | Local form and use | Notes |
|---|---|---|---|
| NISAR L2 GCOV | NASA/ISRO NISAR, distributed by ASF DAAC; inventory in `NISAR_Jamuna_granule_inventory.csv`; can be cut from local HDF5 or streamed using Earthdata/ASF | `cache/sar/kazipur/nisar_<YYYYMMDD>_<track>_HHHH_db.tif`, optional matching `_HVHV_db.tif`, `_receipt.json` | Provisional product CRID P05023. `nisar_subset.py` identifies HH/HV layers, subsets AOI and converts linear power to dB using `10*log10(value)`; metadata/georeferencing and granule identifiers belong in receipt. Missing HV means flooded-vegetation rule unavailable. |
| Terrain and permanent river | Preferred: Earth Engine via `gee_layers.py`: MERIT Hydro HAND, Copernicus GLO-30 DEM, Sentinel-1 dry-season water, Sentinel-2 NDWI, JRC Global Surface Water; optional ASF NISAR water mask | `cache/dem/kazipur/{hand,dem,river_mask,s2_rgb}.tif`, `terrain_receipt.json`; optional `nisar_watermask.tif` | Fallback (`terrain_fallback.py`) derives persistent water from available NISAR and approximate height above the nearest river from GLO-30. `summary.sources`/receipt identifies fallback; do not label fallback as MERIT HAND. DEM is GLO-30, EGM2008 geoid, about 30 m; datum differs from FFWC gauge datum. |
| WorldCover | ESA WorldCover 2021 v200, read by exposure.worldcover() from the public ESA WorldCover S3 cloud-optimized GeoTIFF | `cache/landcover/kazipur/worldcover.tif` and receipt | Categorical 10 m land cover resampled to analysis grid. Historical 2021 class, not current field survey. |
| Buildings | Google Open Buildings v3, acquired by `buildings.py` | `cache/vector/buildings_kazipur.csv` and GeoJSON | Confidence cutoff is 0.7. This is model-detected footprint data from earlier imagery, not damage or current occupancy. |
| Unions/upazilas | geoBoundaries Bangladesh ADM4 clipped to AOI; optional local file | `cache/vector/unions.geojson`, expected properties include `shapeID`, `shapeName`, and upazila name | A site is assigned by the plurality of rasterized administrative pixels; an absent file yields null admin names. Not GADM. |
| Sentinel optical | Earth Engine Sentinel-2 L2A and Landsat 8/9 C2 L2 for whole scenes; Sentinel-2 for legacy composites | `cache/optical/kazipur/` scenes/composites and receipts; rendered into `outputs/kazipur/overlays/` | Optical context only. Legacy composite gaps remain transparent; whole scenes retain their pixels after scene-level cloud screening. Optical data do not generate SAR classifications. Scene may be offset from radar acquisition date; API overlay metadata carries offset/cloud info. |
| Weather | Open-Meteo daily precipitation, NASA POWER `PRECTOTCORR`; fetches go through `src/acquire/safe.py` | `cache/api/*.json`, plus `demo_fixtures/*.json`; summarized under `summary.json` and used by experimental model features | `safe.fetch_json`: online first, then local cache, then fixture; `OFFLINE=1` skips live fetch. Inspect `mode` (`live`, `cache`, `fixture`, or combined) before calling data current. |
| Discharge | GloFAS via Open-Meteo in `forecast.py` | Forecast JSON driver and per-pass `q` values | Used for predictive stage proxy and date-comparison water-level context, not as a measured local gauge stage. |
| InSAR coherence | NISAR GUNW pairs acquired by `gunw_coherence.py` | `cache/coherence/kazipur/coh_<track>_<date1>_<date2>.tif`; optional overlays/site attributes | Observation/context only; crops, wet soil and water also decorrelate. It does not feed headline bank-loss or forecast values. |
| Base map tiles | Esri online map or locally cached NASA GIBS tiles; own Sentinel optical overlays | `web/tiles/` and UI basemap | Esri is not bulk cached. Offline fallback base map is project imagery; see offline dry run. |

The CSV `NISAR_Jamuna_granule_inventory.csv` documents discovered granules; it is not itself a computed water dataset. Receipt objects are the appropriate place to display acquisition source, scene/granule ID, product version, dates, track and processing metadata when present.

## 4. Calculations and formulas

### 4.1 Common grid and area conversion

All analysis rasters are put on the configured 20 m grid in EPSG:32645. Per-pixel area is `pixel_m² = 20 × 20 = 400 m²`; therefore `area_km² = pixel_count × 400 / 1,000,000` and `area_ha = pixel_count × 400 / 10,000`. Reprojection defaults to average resampling for continuous values and nearest neighbour for masks/classes; some layers explicitly select another method.

### 4.2 Track-specific open-water threshold

`run_aoi.py` chooses the earliest available pass for each full-coverage track as baseline. It derives one `T_HH` per track and reuses it on every pass of that track:

1. Prefer the valley between dark-water and land modes in the HH histogram (0.25 dB bins, 5-bin smoothing; candidate must be below 80% of the smaller peak).
2. If unavailable, repeat on pixels within 2 km of the permanent river mask.
3. If unavailable but sample medians exist, use `(median(channel HH) + median(stable-land HH)) / 2`.
4. Otherwise use Otsu over −30 to 0 dB.

The selected threshold and method are exported in `summary.json.thresholds_by_track[track]`; `summary.json.threshold` is a backwards-compatible headline threshold. Do not silently substitute a generic Sentinel-1 threshold. Areas are evaluated at `T_HH−1`, `T_HH`, and `T_HH+1 dB`; the low/high values form the sensitivity range. This is a threshold sensitivity range, not a statistical confidence interval.

For each scene, a 3×3 median filter is applied to HH. Open water is `smoothed_HH < T_HH`; connected water patches smaller than 2,000 m² are removed. Pixels without finite HH are unknown, not dry. If HV exists, values at/below −23 dB are masked before HH−HV is calculated.

### 4.3 Change masks

Only same-track before/after scenes are comparable. On pixels valid in both dates:

- **New water (N2O):** `after_open_water AND NOT before_open_water`.
- **Receded water (O2N):** `before_open_water AND NOT after_open_water`.
- **Other new water:** N2O excluding mainland bank-loss pixels and before-date char land.
- **Char land:** land components that do not touch the west/east AOI edge. Char change is `char_land_before_area − char_land_after_area`; positive means net land lost.

Land/water cleanup removes water components below 2 ha and applies 3×3 closing. Mainland is a land component connected to either west or east edge of the AOI. The main channel is the 8-connected water component with greatest overlap with permanent river mask (largest component fallback).

### 4.4 Mainland bank loss (the only value called erosion)

Candidate bank loss is the intersection of:

1. Land in the before image classified as **mainland**;
2. Open water in the after image (and, when available, the later confirmation image);
3. Water connected to the after-date main channel;
4. Within 1,500 m of the before-date mainland bankline;
5. At least 2 pixels and touching the before bankline (within one 8-connected pixel).

Candidates that fail the bankline-touch condition are moved into `other_new_water`, not counted as bank loss. `bank_loss_confirmed=true` only when a later same-track pass is included. A pair without that later pass is explicitly **UNCONFIRMED**. The reported range is computed by rerunning this rule at threshold −1/0/+1 dB.

River level can change between images. Water expansion may reflect stage rather than permanent bank retreat; compare GloFAS context and, when quoting impacts, FFWC Sirajganj gauge data on compatible datum. A flow ratio of 1.3 or more triggers `stage_warning` on custom comparisons.

### 4.5 Flooded vegetation (experimental)

Only computed when both dates have HV. The after pixel must not be open water and must satisfy:

`HH_after > −8 dB` AND `HH_after − HV_after > 6 dB` AND `HH_after − HH_before ≥ 3 dB`.

This is a double-bounce heuristic and can label flooded aman paddy. Treat as an experimental area estimate, not verified flood damage. If HV is missing, field is null and the rule explains why.

### 4.6 Exposure/context around bank-loss sites

Connected bank-loss components are polygonized and sorted largest first as `S01`, `S02`, …; char-land-lost components use `C01`, … . Land-cover hectares are per WorldCover class inside the mask: pixel count × pixel area / 10,000. Building counts/areas are building centroids in the site mask, using Open Buildings confidence ≥0.7. Output building GeoJSON includes footprints within 300 m of the bank-loss sites for map context. This measures footprints near affected land; it is not a count of damaged structures or residents.

Each site may include `area_ha`, centroid `lat`/`lon`, `land_cover.ha`, `max_retreat_m`, `building_count`, `building_area_m2`, `union`, `upazila`, and optional `mean_coherence`/`coherence_pairs`/`chips`. `max_retreat_m` is the maximum distance-transform value for candidate pixels from the before bankline. Site polygons and values are generated from the middle threshold mask; total pair ranges still carry ±1 dB sensitivity.

### 4.7 Forecasts: two separate experimental products

**30-day forecast** (`src/compute/forecast.py`, exposed as `forecast.json`) is the primary future-water timeline product. The deterministic baseline:

1. Builds a connected drainage height surface from HAND and permanent river.
2. For each NISAR pass, finds the height threshold `h` that maximizes CSI against observed water outside permanent channel.
3. Fits a monotone isotonic relationship `h(Q)` to GloFAS discharge `Q`.
4. For future discharge low/median/high, maps connected land at or below predicted height. LOO and walk-forward validation are retained in output.

The ML challenger in `water_ml.py` is a scikit-learn HistGradientBoostingClassifier for pixel water probability. Features include HAND, distance to river, DEM, WorldCover, GloFAS current/5-day/10-day/trend, rain 3/7/15-day sums, previous pass water, and days since prior pass. It samples by pass with fixed seed; it uses leave-one-pass-out validation. It replaces baseline only when its CSI beats baseline on most held-out passes. `forecast.json.model_used` and `class_rule` tell the UI what is actually shown. Forecast extent is water only—never bank erosion.

**Legacy 7-day layer** (`flood_prob.py`) is a different logistic probability surface. Its calculation is:

`RI_t = 0.75 × RI_(t−1) + rain_t / max(heavy_rain_mm, 15)`  
`z = −1 + 2×RI − 0.6×HAND_m − 0.8×distance_km + 1.5×wet_now`  
`P = sigmoid(scale × z + bias)`

`scale`/`bias` are refit to SAR masks per pass by deterministic two-parameter logistic Newton fit (fixed sample seed); output contains skill before/after. This is experimental planning context, not official warning. Avoid conflating it with the 30-day `forecast.json`.

## 5. Output data contracts for UI builders

All JSON keys are snake_case. Dates in filenames and most fields are `YYYYMMDD` (UTC radar acquisition); forecast dates are similarly keyed strings. Areas are numeric and units are encoded in field names. Null means unavailable/not computed; it must not render as zero.

| File / endpoint | Main content and UI use |
|---|---|
| `outputs/kazipur/summary.json` / `/api/v1/aoi/kazipur/summary` | AOI, source and threshold metadata, preset pairs, calibration/skill, data freshness, weather and processing context. Use for dashboard defaults and provenance. |
| `pairs/<pair>.json` / `/pairs/{pair}` | Full pair metrics, before/after dates and track, threshold/method, threshold-tested values, rule text, confirmation flag, caveats, receipt(s), exposure totals. |
| `pairs/<pair>_sites.geojson` / `/pairs/{pair}/sites?kind=mainland` | Main-land bank-loss site polygons and properties, typically `Sxx`. |
| `pairs/<pair>_char_sites.geojson` / `/pairs/{pair}/sites?kind=char` | Char-land-lost site polygons, `Cxx`; char change is not reliable as a headline statistic. |
| `pairs/<pair>_buildings.geojson` / `/pairs/{pair}/buildings` | Building footprint context near sites; empty FeatureCollection if absent. |
| `pairs/<pair>_banklines.geojson` | Before/after river-facing bankline FeatureCollection. Custom compare also stores companions. |
| `union_summary.json` / `/unions` | Union-level observation ranges and evidence receipts; status may be null/unimplemented. Deprecated erosion aliases may still exist. |
| `overlays.json` / `/overlays` | Layer catalogue: `id`, human `label`, `group`, relative URL, WGS84 `[west,south,east,north]` bounds, and optional date/track/pair/legend metadata. API prefixes URLs with `/outputs/kazipur/`. |
| `overlays/*.png`, `*.webp` | Rendered map rasters, transparent where not part of overlay. Use catalogue bounds, not guessed AOI bounds. |
| `timeline.json` / `/timeline` | Observed passes, expected passes, radar gap, forecast dates. Status can be awaiting data, expected pass, or radar gap. |
| `forecast/forecast.json` / `/forecast` | Driver/model description and validation plus daily discharge/height/water area ranges and overlay references. Render label and `model_used` prominently. |
| `layers/*.tif` | Georeferenced internal/point query layers, not ideal for a web UI without tiling/encoding. |
| `/api/v1/location-status?lat=<>&lon=<>` | Point context: AOI coverage, river/channel, terrain and nearest/latest observation status; outside AOI returns `covered:false`. |
| `/api/v1/aoi/kazipur/compare?track=069A&before=YYYYMMDD&after=YYYYMMDD[&confirm=YYYYMMDD]` | Same-track custom comparison. Invalid/missing date or before≥after returns HTTP 400. May attach cached=true and stage warning. |
| `/api/v1/aois` | Available AOIs, bbox and whether summary has been generated. |
| `/api/v1/aoi/kazipur/insights` | Derived reach-level statistics; corresponding CSVs live under `outputs/kazipur/insights/`. |
| `/api/v1/map-config`, `/gibs-cache` | Offline/basemap configuration and locally available GIBS tile index. |
| `/api/v1/aoi/kazipur/ingest` | POST localhost-only to initiate background ingest; GET polls status. Not needed for a read-only external UI. |

### Headline pair fields

| Field | Meaning / rendering guidance |
|---|---|
| `new_water_km2_range` | Total newly classified open water; includes multiple change types. Sensitivity range; not identical to bank-loss area. |
| `receded_km2_range` | Pixels classified water before and not water after. |
| `mainland_bank_loss_ha_range` | Candidate mainland bank-loss area under the explicit rule. Show range, hectares, dates, track and confirmation badge together. |
| `mainland_bank_loss_ha_mid` | Area at the nominal central threshold T_HH, using index 1 of the three tested values. It is neither the maximum nor the arithmetic midpoint of the range. |
| `bank_loss_confirmed` | Boolean; false means no later same-track confirmation pass was available/included. |
| `bank_loss_rule` | Machine-generated human-readable rule description; expose via details/help, not as a substitute for the badge. |
| `char_area_change_ha_range` | Net char land before minus after; positive = land loss. `char_change_reliable:false`; context/overlay only. |
| `other_new_water_km2_range` | N2O that is neither retained mainland bank loss nor before-char land. |
| `flooded_vegetation_km2_range` | Experimental heuristic. Null if HV absent. |
| `threshold_db`, `threshold_tested_db`, `threshold` | Track cutoff and tested sensitivity values/method. Display source/track where useful. |
| `unknown_pixel_pct` | Highest no-data fraction in before/after comparison. High unknown means partial coverage; do not interpret missing pixels as dry. |
| `caveat`, `stage_warning` | Context warnings; keep accessible beside results. |
| deprecated `erosion_ha_range`, `erosion_rule`, `erosion_ha_range_jun_oct` | Compatibility aliases. Build on `mainland_bank_loss_*` names. |

### Overlay groups and default interpretation

Groups are specified in `overlays.json`. Common groups: `base`, `sar_grey`, `water_date`, `change`, `coherence`, `optical_date`, and forecast overlays referenced in forecast JSON. Typical colors from current pipeline: new water cyan `#00bcd4`; mainland bank loss red `#ff1744`; char lost orange `#ff9100`; char gained yellow `#ffea00`; flooded vegetation magenta `#e040fb`; per-date open water blue `#1e78ff`; low coherence orange. Always pair color with legend/label because layers can overlap. Coherence is observation only and open water is hidden in that layer.

## 6. Recommended UI behavior

- Label observations **Observed** and all future layers **Predictive / experimental**. State the forecast horizon and model in view.
- For bank loss, show low–high hectares, dates/track, `UNCONFIRMED` when false, and stage warning/caveat near the number. Do not make the middle-threshold component total the headline; sites are middle-threshold geometry while the range is the sensitivity metric.
- For char change, show it as unstable context/overlay, with positive/negative convention visible. Never label it confirmed erosion.
- Treat null as “not available/not computed”; zero is a valid computed value. Distinguish unknown/no-data from dry.
- Show source freshness (`mode`, acquisition date, generated timestamp, receipt) and threshold method. Cached/fixture inputs are not live updates.
- Use `overlays[].bounds` for georeferencing each image. GeoJSON is WGS84. The analysis grid and area calculations are metric, not degrees.
- Compare only same-track dates. Put discharge/stage context next to change because flow differences can dominate apparent change.
- Building context means mapped footprints from older data, not losses. Avoid damage/people-at-risk claims.
- Expose source citations/licensing in About/Data Sources; see the handoff attribution table.

## 7. Folder map and generated vs source-of-truth files

```text
D:\\deltasar\\
  README.md, requirements.txt, NISAR_Jamuna_granule_inventory.csv
  src\\acquire\\     source downloads and preparation
  src\\compute\\     deterministic rules and experimental models
  src\\pipeline\\    orchestration and publication
  src\\api\\         FastAPI contracts
  web\\index.html     current browser UI; vendor MapLibre assets
  Data\\Track69\\      local NISAR L2 GCOV scenes for 069A (18 Jun, 12 Jul, 29 Aug, 10 Sep, 22 Sep, 4 Oct, 16 Oct 2026) plus consecutive NISAR GUNW interferograms used for coherence
  cache\\             downloaded/cut inputs and mutable model/calibration state (not portable by default)
  demo_fixtures\\     portable, reproducible offline UI fixture
  outputs\\           current generated run
  outputs_prev\\      archived prior generated run
  dist\\               packaged artifacts
  docs\\               project notes and this data/UI reference
  scripts\\            synthetic fixture, tile caching, handoff packaging, compare precompute
```

Do not use `outputs_prev` or a screenshot as the analytical source of truth. The pipeline and receipts are. `demo_fixtures/outputs` is intentionally usable by a portable demo. Synthetic data from `make_synthetic_demo.py` is wholly artificial and must never be presented as observed Jamuna data.

## 8. Reproduction and basic operation

Install Python 3.10–3.12 and `requirements.txt`. For an existing portable fixture:

```powershell
$env:DELTASAR_OUTPUTS = 'demo_fixtures\outputs'
$env:OFFLINE = '1'
python -m uvicorn src.api.main:app --port 8000
```

Then browse `http://127.0.0.1:8000/`; interactive API schema is `/docs`. For an actual new processing run, inputs must be acquired first and `python -m src.pipeline.run_aoi --replay` can build pair outputs/calibration; `python -m src.compute.forecast` builds the 30-day forecast/timeline. `publish.py` stages and swaps output directories for server safety. Follow setup and source acquisition in [HANDOFF.md](HANDOFF.md), and offline constraints in [OFFLINE_DRYRUN.md](OFFLINE_DRYRUN.md).

## 9. Known limitations and interpretation boundaries

- NISAR product is provisional; 20 m AOI grid and threshold sensitivity limit spatial/area precision.
- Threshold ±1 dB range is sensitivity, not a confidence interval or probability statement.
- A river-stage difference can mimic permanent retreat. Gauge verification is essential for impact claims.
- Mainland/char classification depends on AOI edge connectivity; geometry at edges can affect mainland designation.
- Char area is explicitly flagged unreliable because narrow channels can split/join components as threshold changes and seasonal submergence alters mapped area.
- Flooded-vegetation logic is experimental; dry/flooded crops can produce similar radar response.
- Buildings are model footprints from prior imagery, not damage observations.
- Fallback terrain is approximate and must be visibly identified as fallback.
- The 30-day model has limited pass history and is validated only against held-out radar passes; it is not an operational forecast. Official warnings remain FFWC/BMD.
- The 7-day legacy layer and coherence are supporting/experimental layers, not bank-loss evidence.
- Cached/fixture weather can be stale; display its source mode and generated time.

## 10. Source attribution

Use the complete licence and attribution table in [HANDOFF.md — Data licences and attribution](HANDOFF.md#data-licences-and-attribution). Key attribution sources include NASA/JPL-Caltech and ISRO via ASF for NISAR; Copernicus/DLR/Airbus for GLO-30; Yamazaki et al. for MERIT Hydro; ESA WorldCover; Google Open Buildings; geoBoundaries; GloFAS/Copernicus EMS; Open-Meteo; NASA POWER; and MapLibre contributors. Esri imagery carries Esri's own terms and attribution.

## 11. Keeping this reference accurate

When formulas/constants change, update Sections 3–5 from code, particularly `src/config.py`, `src/compute/water.py`, `src/compute/forecast.py`, `src/compute/water_ml.py`, `src/compute/flood_prob.py` and `src/api/main.py`. When payload keys change, update the field tables and links. Treat code receipts and API output as the authority for a particular generated run.


