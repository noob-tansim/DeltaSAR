"""Rainfall inputs, both free and keyless.

- Open-Meteo: last 3 days (antecedent rain) + next 7 days forecast.
- NASA POWER: 2 years of daily rain (PRECTOTCORR) -> local "heavy rain" threshold (P90 of wet days).

Run:  python -m src.acquire.weather 24.64 89.69
"""
from __future__ import annotations

import datetime as dt
import sys

import numpy as np

from src.acquire.safe import fetch_json


def get_rain(lat: float, lon: float) -> dict:
    # Round so nearby clicks share one cached file (both APIs are coarse grids anyway).
    la, lo = round(lat * 4) / 4, round(lon * 4) / 4

    meteo, m1 = fetch_json(
        "https://api.open-meteo.com/v1/forecast",
        {"latitude": la, "longitude": lo, "daily": "precipitation_sum",
         "timezone": "Asia/Dhaka", "past_days": 3, "forecast_days": 7},
        name=f"meteo_{la:.2f}_{lo:.2f}",
    )
    days = meteo["daily"]["time"]
    rain = [float(x or 0.0) for x in meteo["daily"]["precipitation_sum"]]

    # POWER lags a few days behind real time, so end 7 days ago.
    end = dt.date.today() - dt.timedelta(days=7)
    start = end - dt.timedelta(days=730)
    power, m2 = fetch_json(
        "https://power.larc.nasa.gov/api/temporal/daily/point",
        {"parameters": "PRECTOTCORR", "community": "AG", "latitude": la, "longitude": lo,
         "start": start.strftime("%Y%m%d"), "end": end.strftime("%Y%m%d"), "format": "JSON"},
        name=f"power_{la:.2f}_{lo:.2f}",
    )
    series = power["properties"]["parameter"]["PRECTOTCORR"]
    vals = np.array([v for v in series.values() if v is not None and v >= 0], dtype=float)
    wet = vals[vals >= 1.0]
    heavy_p90 = float(np.percentile(wet, 90)) if wet.size else 45.0

    return {
        "lat": la, "lon": lo,
        "antecedent_dates": days[:3], "antecedent_mm": rain[:3],
        "forecast_dates": days[3:], "forecast_mm": rain[3:],
        "baseline_2yr_mean_daily_mm": round(float(vals.mean()), 2) if vals.size else None,
        "baseline_heavy_p90_mm": round(heavy_p90, 1),
        "baseline_period": [start.isoformat(), end.isoformat()],
        "sources": {"forecast": "Open-Meteo", "baseline": "NASA POWER PRECTOTCORR"},
        "mode": "live" if m1 == m2 == "live" else f"{m1}/{m2}",
    }


def observed_rain(lat: float, lon: float, end_yyyymmdd: str, days: int = 10) -> dict:
    """NASA POWER daily rain for the `days` days ending on a past date (season replay / calibration)."""
    la, lo = round(lat * 4) / 4, round(lon * 4) / 4
    end = dt.date(int(end_yyyymmdd[:4]), int(end_yyyymmdd[4:6]), int(end_yyyymmdd[6:]))
    start = end - dt.timedelta(days=days - 1)
    data, mode = fetch_json(
        "https://power.larc.nasa.gov/api/temporal/daily/point",
        {"parameters": "PRECTOTCORR", "community": "AG", "latitude": la, "longitude": lo,
         "start": start.strftime("%Y%m%d"), "end": end.strftime("%Y%m%d"), "format": "JSON"},
        name=f"power_{la:.2f}_{lo:.2f}_{end_yyyymmdd}_{days}d",
    )
    s = data["properties"]["parameter"]["PRECTOTCORR"]
    return {"dates": list(s.keys()), "mm": [max(0.0, float(v)) for v in s.values()], "source": "NASA POWER", "mode": mode}


if __name__ == "__main__":
    lat, lon = (float(sys.argv[1]), float(sys.argv[2])) if len(sys.argv) > 2 else (24.64, 89.69)
    import json
    print(json.dumps(get_rain(lat, lon), indent=1))
