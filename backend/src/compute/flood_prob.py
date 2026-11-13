"""7-day deterministic flood likelihood + recalibration whenever a new full-track SAR pass arrives.

Model (per pixel, per day t):
    RI_t = k * RI_{t-1} + rain_t / heavy_mm                      (rain index, k = 0.75 memory)
    z_t  = b0 + b_rain*RI_t - b_hand*HAND_m - b_dist*dist_km + b_wet*wet_now
    P_t  = 1 / (1 + exp(-(scale * z_t + bias)))

The b-coefficients are physical priors (more rain, wetter now -> higher; higher above the river,
farther from it -> lower). No AI produces them. `scale` and `bias` are refitted on each new SAR
pass by a 2-parameter logistic fit to the SAR water mask; skill (Brier, CSI, hit rate, false
alarm ratio) is reported before and after so the change is shown, not claimed.

This is an EXPERIMENTAL planning layer. Official warnings stay with FFWC/BMD, and the
27 Jul - 10 Aug radar gap is never filled by this model.

State (scale, bias, history) lives in cache/calibration_<aoi>.json.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

import numpy as np

from src.config import CACHE

PERMANENT_WATER_HAND = 0.0


@dataclass
class Params:
    k: float = 0.75
    b0: float = -1.0
    b_rain: float = 2.0
    b_hand: float = 0.6     # per metre above nearest drainage
    b_dist: float = 0.8     # per km from river/khal
    b_wet: float = 1.5
    bias: float = 0.0
    scale: float = 1.0      # fitted together with bias: how sharply terrain/rain separate wet from dry
    history: list = field(default_factory=list)


def _state_path(aoi: str):
    return CACHE / f"calibration_{aoi}.json"


def load_params(aoi: str) -> Params:
    p = _state_path(aoi)
    return Params(**json.loads(p.read_text())) if p.exists() else Params()


def save_params(aoi: str, prm: Params) -> None:
    _state_path(aoi).write_text(json.dumps(asdict(prm), indent=1))


def rain_index(antecedent_mm: list[float], forecast_mm: list[float], heavy_mm: float, k: float) -> list[float]:
    ri, out = 0.0, []
    for r in antecedent_mm:              # warm up with the last 3 observed days
        ri = k * ri + r / max(heavy_mm, 15.0)
    for r in forecast_mm:
        ri = k * ri + r / max(heavy_mm, 15.0)
        out.append(ri)
    return out


def _z(ri, hand_m, dist_m, wet_now, prm: Params, bias: float):
    return (prm.b0 + prm.b_rain * ri - prm.b_hand * hand_m - prm.b_dist * (dist_m / 1000.0)
            + prm.b_wet * wet_now + bias)


def probability_7d(hand_m: np.ndarray, dist_m: np.ndarray, wet_now: np.ndarray,
                   antecedent_mm, forecast_mm, heavy_mm: float, prm: Params) -> np.ndarray:
    """Returns float32 array (7, H, W) of probabilities 0..1. Permanent water is set to NaN."""
    ris = rain_index(antecedent_mm, forecast_mm, heavy_mm, prm.k)
    hand = np.nan_to_num(hand_m, nan=10.0)
    dist = np.nan_to_num(dist_m, nan=5000.0)
    wet = np.nan_to_num(wet_now, nan=0.0).astype(float)
    hand, dist, wet = hand.astype("float32"), dist.astype("float32"), wet.astype("float32")
    out = np.empty((len(ris),) + hand.shape, dtype="float32")          # float32, filled day by day (memory)
    for i, ri in enumerate(ris):
        out[i] = 1 / (1 + np.exp(-(prm.scale * _z(np.float32(ri), hand, dist, wet, prm, 0.0) + prm.bias)))
    return out


def skill(pred_prob: np.ndarray, observed: np.ndarray, valid: np.ndarray, cut: float | None = None) -> dict:
    """Brier + Brier skill score vs the observed-frequency climatology, and categorical scores
    (CSI, hit rate, FAR) at a frequency-matched cutoff: the probability quantile at which the predicted
    wet fraction equals the observed wet fraction (a fixed 0.5 cut gives CSI 0 whenever floods are rare)."""
    p, o = pred_prob[valid], observed[valid].astype(float)
    obs = o >= 0.5
    f = float(obs.mean()) if obs.size else 0.0
    if cut is not None:
        method = "fixed (given)"
    elif 0.0 < f < 1.0:
        cut, method = float(np.quantile(p, 1.0 - f)), "frequency-matched (predicted wet fraction = observed)"
    else:
        cut, method = 0.5, "fixed 0.5 (observed fraction is 0 or 1)"
    yes = p >= cut
    hits = int((yes & obs).sum()); misses = int((~yes & obs).sum()); fa = int((yes & ~obs).sum())
    brier = float(np.mean((p - o) ** 2))
    return {
        "brier": round(brier, 4),
        "brier_skill_score": round(1.0 - brier / (f * (1.0 - f)), 3) if 0.0 < f < 1.0 else None,
        "cutoff": round(cut, 4), "cutoff_method": method,
        "csi": round(hits / max(hits + misses + fa, 1), 3),
        "hit_rate": round(hits / max(hits + misses, 1), 3),
        "false_alarm_ratio": round(fa / max(hits + fa, 1), 3),
        "pred_flood_frac": round(float(yes.mean()), 4),
        "obs_flood_frac": round(float(obs.mean()), 4),
    }


def _fit_scale_bias(z0: np.ndarray, y: np.ndarray, iters: int = 25) -> tuple[float, float]:
    """2-parameter logistic fit p = sigmoid(scale*z0 + bias) by Newton's method (deterministic)."""
    a, b = 1.0, 0.0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(a * z0 + b)))
        w = np.clip(p * (1 - p), 1e-6, None)
        g = np.array([np.sum((y - p) * z0), np.sum(y - p)])
        H = np.array([[np.sum(w * z0 * z0), np.sum(w * z0)], [np.sum(w * z0), np.sum(w)]]) + 1e-6 * np.eye(2)
        da, db = np.linalg.solve(H, g)
        a, b = float(np.clip(a + da, 0.05, 20)), float(np.clip(b + db, -20, 20))
        if abs(da) < 1e-5 and abs(db) < 1e-5:
            break
    return a, b


def calibrate(aoi: str, ri_on_pass_day: float, hand_m, dist_m, wet_before, observed_water,
              valid, pass_date: str, prm: Params | None = None, sample: int = 300_000) -> dict:
    """Compare the model with a new SAR pass, then refit (scale, bias) to the observed water.

    observed_water: bool mask of water beyond the permanent channel on pass_date (from SAR).
    valid: land pixels to evaluate (no permanent water, no no-data).
    Skill is reported before and after the refit, so the improvement is visible, not claimed.
    """
    prm = prm or load_params(aoi)
    hand = np.nan_to_num(hand_m, nan=10.0); dist = np.nan_to_num(dist_m, nan=5000.0)
    wet = np.nan_to_num(wet_before, nan=0.0).astype(float)
    z0 = _z(ri_on_pass_day, hand, dist, wet, prm, 0.0)[valid]
    y = observed_water[valid].astype(float)
    ones = np.ones(z0.shape, bool)
    before = skill(1 / (1 + np.exp(-(prm.scale * z0 + prm.bias))), y, ones)

    rng = np.random.default_rng(0)                      # fixed seed: same data -> same answer
    idx = rng.choice(z0.size, size=min(sample, z0.size), replace=False)
    a, b = _fit_scale_bias(z0[idx], y[idx])
    if prm.history:                                     # smooth across passes
        a, b = 0.5 * (a + prm.scale), 0.5 * (b + prm.bias)

    after = skill(1 / (1 + np.exp(-(a * z0 + b))), y, ones)
    note = None
    if after["brier"] > before["brier"]:           # Newton fit diverged (near-separable sample): keep the prior
        note = f"refit rejected: Brier {after['brier']} > {before['brier']} before; kept previous scale/bias"
        a, b, after = prm.scale, prm.bias, before
    entry = {"pass_date": pass_date, "scale_before": round(prm.scale, 3), "bias_before": round(prm.bias, 3),
             "scale_after": round(a, 3), "bias_after": round(b, 3),
             "skill_before": before, "skill_after": after, "note": note,
             "error_margin_pct": round(100 * np.sqrt(after["brier"]), 1)}
    prm.scale, prm.bias = a, b
    prm.history.append(entry)
    save_params(aoi, prm)
    return entry


def update_hand_for_erosion(hand_m: np.ndarray, water_prev: np.ndarray, water_now: np.ndarray,
                            water_baseline: np.ndarray) -> tuple[np.ndarray, int]:
    """Bank erosion: land in the baseline that is water in two consecutive passes becomes river
    (HAND = 0). Two passes, not one, so a single flood day isn't mistaken for erosion."""
    eroded = water_prev & water_now & ~water_baseline
    out = hand_m.copy()
    out[eroded] = PERMANENT_WATER_HAND
    return out, int(eroded.sum())
