"""Live data sources: ask each real service the app depends on for something real about the reach.

Skipped by default (they need the internet and the services' good will). Run them with:
    LIVE_TESTS=1 python -m pytest tests/test_live_sources.py -v
CI runs them once a day (.github/workflows/live-sources.yml), so a broken upstream shows up before a demo does.
"""
from __future__ import annotations

import datetime as dt
import os
import time

import pytest
import requests

pytestmark = pytest.mark.skipif(os.environ.get("LIVE_TESTS") != "1", reason="set LIVE_TESTS=1 to call live services")

BBOX = (89.46, 24.205, 89.918, 24.80)
UA = {"User-Agent": "DeltaSAR-live-test/1.0"}
UTC = dt.timezone.utc


def get(url: str, **kw):
    r = requests.get(url, headers=UA, timeout=kw.pop("timeout", 60), **kw)
    r.raise_for_status()
    return r


def test_cmr_has_recent_nisar_gcov_over_the_reach():
    """NASA CMR: the NISAR L2 GCOV collections list granules over the reach, newest within 45 days."""
    newest = None
    for short in ("NISAR_L2_GCOV_V1", "NISAR_L2_GCOV_PROVISIONAL_V1"):
        j = get("https://cmr.earthdata.nasa.gov/search/granules.umm_json", params={
            "short_name": short, "bounding_box": ",".join(map(str, BBOX)), "sort_key": "-start_date", "page_size": 1}).json()
        for it in j.get("items", []):
            t = dt.datetime.fromisoformat(it["umm"]["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"].replace("Z", "+00:00"))
            assert "GCOV" in it["umm"]["GranuleUR"]
            newest = max(newest, t) if newest else t
    assert newest is not None, "no NISAR GCOV granule over the reach"
    assert (dt.datetime.now(UTC) - newest).days <= 45, f"newest NISAR pass is old: {newest:%Y-%m-%d}"


def test_asf_search_lists_nisar_gcov():
    """ASF Search API (Vertex): NISAR GCOV scenes intersect the reach."""
    w, s, e, n = BBOX
    j = get("https://api.daac.asf.alaska.edu/services/search/param", params={
        "dataset": "NISAR", "processingLevel": "GCOV", "maxResults": 3, "output": "geojson",
        "intersectsWith": f"POLYGON(({w} {s},{e} {s},{e} {n},{w} {n},{w} {s}))"}).json()
    feats = j.get("features", [])
    assert feats, "ASF returned no NISAR GCOV scene"
    assert {f["properties"]["pathNumber"] for f in feats} <= {69, 19, 170, 91}


def test_gibs_serves_the_nisar_picture():
    """NASA GIBS: the NISAR GCOV layer has a picture of the Jamuna for a known pass date."""
    r = get("https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/NISAR_L2_Geocoded_Polarimetric_Covariance/default/"
            "2026-07-24/GoogleMapsCompatible_Level13/9/220/383.png")
    assert r.headers.get("content-type", "").startswith("image/") and len(r.content) > 10_000


def test_eonet_floods():
    """NASA EONET: the floods category answers and lists events."""
    j = get("https://eonet.gsfc.nasa.gov/api/v3/events", params={"category": "floods", "status": "all", "limit": 20, "days": 400}).json()
    assert isinstance(j.get("events"), list) and j["events"]


def test_power_daily_rain_at_the_reach():
    """NASA POWER: daily corrected precipitation at the reach centre, values in range."""
    end = dt.date.today()
    start = end - dt.timedelta(days=20)
    j = get("https://power.larc.nasa.gov/api/temporal/daily/point", params={
        "parameters": "PRECTOTCORR", "community": "AG", "longitude": 89.69, "latitude": 24.5,
        "start": start.strftime("%Y%m%d"), "end": end.strftime("%Y%m%d"), "format": "JSON"}).json()
    vals = [v for v in j["properties"]["parameter"]["PRECTOTCORR"].values() if v != -999]
    assert vals and all(0 <= v <= 500 for v in vals)


def test_imerg_through_climateserv():
    """NASA IMERG Early (via NASA SERVIR ClimateSERV): the same request jobs/j2 makes, for the last 10 days."""
    from jobs.j2_load_inputs import fetch_rain
    end = dt.date.today() - dt.timedelta(days=2)
    rows = fetch_rain(end - dt.timedelta(days=10), end)
    assert rows, "ClimateSERV returned no IMERG values"
    assert all(0 <= mm <= 500 for _, mm in rows)


def test_ffwc_public_pages_reachable():
    """FFWC (BWDB): the public water-level tables load. Values may be stale; the app marks them so."""
    t0 = time.time()
    try:
        r = requests.get("http://old.ffwc.gov.bd/ffwc_charts/waterlevelobs.php", headers=UA, timeout=45)
    except requests.RequestException as exc:
        pytest.xfail(f"FFWC not reachable from here ({type(exc).__name__}); the app falls back to data/river_levels.csv")
    assert r.status_code == 200 and ("Kazipur" in r.text or "Serajganj" in r.text), f"unexpected FFWC page after {time.time() - t0:.0f} s"
