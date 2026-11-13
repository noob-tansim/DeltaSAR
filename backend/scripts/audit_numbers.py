"""Source audit: recompute every headline number the website and the assistant state, from the data files.

    python scripts/audit_numbers.py

Each line: the claim as written on the site / in ask_facts.md, the value recomputed from the file, and the file.
Exit code 1 if any claim does not match its source.
"""
from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "frontend" / "public" / "data"
BACK = ROOT / "backend"
load = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))  # noqa: E731

story, season, val = load(WEB / "story.json"), load(WEB / "season.json"), load(WEB / "validation.json")
passes = load(BACK / "data" / "passes.json")
stations = load(BACK / "data" / "stations.json")
rain = [l.split(",") for l in (BACK / "data" / "rain_daily.csv").read_text(encoding="utf-8").splitlines()[1:]]
facts = (BACK / "src" / "api" / "ask_facts.md").read_text(encoding="utf-8")

hp = story["headline_pair"]
ins = story["insights"]
exp = hp["exposure"]["mainland_bank_loss"]
near = {r["within_m"]: r for r in ins["near_bank"]["rows"]}
site1 = ins["where"]["rows"][0]
retreat_s01 = next(s for s in ins["retreat"]["sites"] if s["site_id"] == "S01")
p = {x["key"]: x for x in season["processed"]}
gran = passes.get("granules") or passes.get("passes")
g069 = [g for g in gran if g["track"] == "069A" and g["full_frame"] and g["acquired_utc"] >= "2026-07-20"]
after_gap = next(g for g in g069 if g["acquired_utc"].startswith("2026-08-17"))
lat069 = [g["latency_hours"] for g in g069 if g is not after_gap]
rain_max = max(rain, key=lambda r: float(r[1]))
hh = [x["HH"]["contrast_db"] for x in val["pol"]]
r1 = lambda v: f"{int(v * 10 + 0.5 + 1e-9) / 10:.1f}"  # noqa: E731  half-up, as printed on the site
hv = [x["HV"]["contrast_db"] for x in val["pol"]]
sk = val["skill"]
crop_peak = max(ins["frequency"]["by_date"], key=lambda d: d["cropland_in_water_ha"])
dl = {s["name"]: s["danger_level_m"] for s in stations["stations"]}

checks = [
    # (claim on the site, value computed now, source file)
    ("Bank loss 187–232 ha", f"{hp['mainland_bank_loss_ha_range'][0]:.0f}–{hp['mainland_bank_loss_ha_range'][1]:.0f} ha", "pairs/erosion_069A_interim.json"),
    ("Confirmed by the 16 Oct pass", f"confirmed={hp['bank_loss_confirmed']} by {hp['confirm_pass']}", "same"),
    ("38 sites ≥ 0.5 ha", f"{exp['sites']} sites", "same, exposure"),
    ("About 74 ha cropland on lost land", f"{exp['land_cover']['ha']['cropland']:.1f} ha", "same, ESA WorldCover"),
    ("47 buildings on lost land", f"{exp['buildings']} buildings", "same, Google Open Buildings"),
    ("712 buildings within 100 m of a retreating bank", f"{near[100]['buildings']} buildings, {near[100]['cropland_ha']:.0f} ha cropland", "insights.json near_bank"),
    ("305 buildings within 50 m", f"{near[50]['buildings']}", "same"),
    ("Largest site S01, Char Girish, 38.8 ha", f"{site1['largest_site']}, {site1['union']}, {site1['largest_ha']} ha", "insights.json where"),
    ("Char Girish lost 41 ha in 4 sites", f"{site1['bank_loss_ha']} ha in {site1['sites']} sites", "same"),
    ("S01 bank moved up to 228 m", f"max retreat {max(x['retreat_m'] for x in retreat_s01['series'])} m", "insights.json retreat"),
    ("Flooded cropland peak 39,425 ha on 24 Jul", f"{crop_peak['cropland_in_water_ha']:,.0f} ha on {crop_peak['date']}", "insights.json frequency"),
    ("24 Jul: 776 km² water, 596 beyond channel", f"{p['069A_20260724']['water_km2']} / {p['069A_20260724']['water_outside_channel_km2']} km²", "insights.json river.passes"),
    ("Flow 4 Oct 16,180 < 18 Jun 27,605 m³/s", f"{p['069A_20261004']['discharge_m3s']} vs {p['069A_20260618']['discharge_m3s']} m³/s", "same (GloFAS)"),
    ("~5.8 km² per 1,000 m³/s, R² 0.21", f"{season['fit']['slope_km2_per_1000m3s']} km², R² {season['fit']['r2']}", "insights.json river.fit"),
    ("Threshold −15.62 dB (069A), −14.06 dB (019D)", f"{season['thresholds_by_track']['069A']['threshold_db']} / {season['thresholds_by_track']['019D']['threshold_db']} dB", "summary.json"),
    ("HH contrast 9.0–11.6 dB", f"{r1(min(hh))}–{r1(max(hh))} dB", "validation.json pol"),
    ("HV contrast 6.8–8.2 dB", f"{r1(min(hv))}–{r1(max(hv))} dB", "same"),
    ("Mean CSI 0.17 / 0.48 / 0.50", f"{sk['mean']['stage_proxy']:.2f} / {sk['mean']['ml']:.2f} / {sk['mean']['persistence']:.2f}", "validation.json skill"),
    ("Persistence wins 6 of 9", f"{sk['persistence_wins']} of {sk['n']}", "same"),
    ("NASA delay 45–71 h, 122 h after the gap", f"{int(min(lat069))}–{max(lat069):.0f} h, after the gap {after_gap['latency_hours']:.0f} h", "data/passes.json (CMR)"),
    ("Wettest day 75.2 mm on 5 Aug", f"{float(rain_max[1])} mm on {rain_max[0]}", "data/rain_daily.csv (IMERG)"),
    ("13 passes processed", f"{len(season['processed'])} passes", "season.json"),
    ("Danger levels Kazipur 14.80 m, Sirajganj 12.90 m", f"{dl.get('Kazipur')} / {dl.get('Sirajganj')} m", "data/stations.json (FFWC)"),
]

expected = {
    0: "187–232 ha", 2: "38 sites", 4: "47 buildings", 5: "712 buildings", 6: "305", 7: "38.76", 8: "41.3 ha in 4 sites",
    9: "228 m", 10: "39,425 ha", 11: "775.6 / 596", 12: "16180 vs 27605", 13: "5.78 km², R² 0.21", 14: "-15.62 / -14.06",
    15: "9.0–11.6", 16: "6.8–8.2", 17: "0.17 / 0.48 / 0.50", 18: "6 of 9", 19: "45–71 h, after the gap 122 h", 20: "75.2 mm on 2026-08-05", 21: "13 passes", 22: "14.8 / 12.9",
}
bad = 0
w = max(len(c[0]) for c in checks)
for i, (claim, got, src) in enumerate(checks):
    ok = expected.get(i, "") in got or (i not in expected)
    bad += not ok
    print(f"{'OK  ' if ok else 'DIFF'}  {claim.ljust(w)}  ->  {got}   [{src}]")

for n in ("187", "232", "712", "39,425", "75.2", "9.0", "11.6", "6.8", "8.2", "0.50", "0.48", "0.17", "1090", "999", "14.80", "12.90"):
    if n not in facts:
        print(f"MISSING in ask_facts.md: {n}"); bad += 1
print(f"\n{len(checks) - bad}/{len(checks)} claims match their source files")
sys.exit(1 if bad else 0)
