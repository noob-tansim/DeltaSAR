"""Deterministic surface classes from NISAR L-band backscatter (dB). No model invents a number.

Rules (NISAR Science Users' Handbook logic, as summarised in the team audit):
- Open water: specular, so HH (and HV) very low:            HH < T_HH
- Flooded vegetation (jute, aman, char scrub): double bounce: HH > -8 dB and HH - HV > 6 dB
- HV below the L-band noise floor (-23 dB) is masked before any HH/HV ratio.
- T_HH is measured per reach from the baseline scene (permanent channel vs stable land),
  never borrowed from Sentinel-1's -16 dB, and every area is reported at T_HH -1/0/+1 dB.
- Change classes: N2O land->open water (flood or bank loss), O2N water->land (char emergence).
- Mainland bank loss (the only thing called erosion): land connected to the AOI's west/east edge in the
  before scene that is water in the after AND confirm pass, connected to the main channel, and within
  BANK_LOSS_MAX_RETREAT_M of the before mainland bankline. Char (island) change is reported separately.
- Flooded vegetation is change-based: HH rose by >= FV_HH_RISE_MIN_DB since the before pass.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

from src.config import (BANK_LOSS_MAX_RETREAT_M, FV_HH_HV_MIN_DB, FV_HH_MIN_DB, FV_HH_RISE_MIN_DB,
                        WATER_SPECK_HA)

HV_NOISE_FLOOR_DB = -23.0
EIGHT = np.ones((3, 3), bool)
CAVEAT = ("River stage differs between dates; land-to-water change near the bank includes stage effect. "
          "Compare with the FFWC Sirajganj gauge before quoting.")


def otsu_threshold(db: np.ndarray, lo: float = -30.0, hi: float = 0.0) -> float:
    v = db[np.isfinite(db)]
    v = v[(v > lo) & (v < hi)]
    if v.size < 100:
        return -18.0
    hist, edges = np.histogram(v, bins=256, range=(lo, hi))
    c = (edges[:-1] + edges[1:]) / 2
    w0 = np.cumsum(hist); w1 = w0[-1] - w0
    m0 = np.cumsum(hist * c) / np.maximum(w0, 1)
    m1 = (np.sum(hist * c) - np.cumsum(hist * c)) / np.maximum(w1, 1)
    return float(c[np.argmax(w0 * w1 * (m0 - m1) ** 2)])


def valley_threshold(db: np.ndarray, split: float = -15.0) -> tuple[float, str] | None:
    """Histogram valley between the dark (water) mode below `split` dB and the land mode above it.
    0.25 dB bins, 1.25 dB running mean. Returns None when there is no clear two-peak valley
    (valley bin must be < 80% of the smaller peak). Plain Otsu over -30..0 dB lands inside the land
    mode on the Jamuna (land is ~85% of the AOI), which is why this is the primary method."""
    v = db[np.isfinite(db)]
    if v.size < 1000:
        return None
    hist, edges = np.histogram(v, bins=np.arange(-30.0, 0.25, 0.25))
    hist = np.convolve(hist, np.ones(5) / 5, mode="same")
    c = (edges[:-1] + edges[1:]) / 2
    iw = int(np.argmax(np.where(c < split, hist, -1))); il = int(np.argmax(np.where(c >= split, hist, -1)))
    if iw >= il or hist[iw] <= 0:
        return None
    iv = iw + int(np.argmin(hist[iw:il + 1]))
    if hist[iv] >= 0.8 * min(hist[iw], hist[il]):
        return None
    return round(float(c[iv]), 2), f"histogram valley between water mode {c[iw]:.2f} dB and land mode {c[il]:.2f} dB"


def reach_threshold(hh_db: np.ndarray, permanent_water: np.ndarray, stable_land: np.ndarray,
                    near_river: np.ndarray | None = None) -> dict:
    """T_HH for a track, measured once on its baseline scene and reused for every date of that track.
    1) histogram valley over the whole scene; 1b) the same restricted to `near_river` pixels (e.g. within 2 km of
    the river mask, which balances the water and land populations); 2) midpoint of permanent-channel vs
    stable-land medians; 3) Otsu if both samples are too small. `method` records which one was used."""
    core_water = ndimage.binary_erosion(permanent_water, iterations=3)   # stay off the banks
    w, l = hh_db[core_water & np.isfinite(hh_db)], hh_db[stable_land & np.isfinite(hh_db)]
    med = {}
    if w.size > 500 and l.size > 500:
        med = {"water_median_db": round(float(np.median(w)), 2), "land_median_db": round(float(np.median(l)), 2),
               "n_water_px": int(w.size), "n_land_px": int(l.size)}
    vt = valley_threshold(hh_db)
    if vt is not None:
        return {"threshold_db": vt[0], "method": vt[1] + " (whole scene)", **med}
    if near_river is not None:
        vn = valley_threshold(np.where(near_river, hh_db, np.nan))
        if vn is not None:
            return {"threshold_db": vn[0], "method": vn[1] + " (pixels within 2 km of the river mask; no valley "
                                                              "over the whole scene)", **med}
    if med:
        return {"threshold_db": round((med["water_median_db"] + med["land_median_db"]) / 2, 2),
                "method": "midpoint of channel vs stable-land medians (no clear histogram valley, whole scene "
                          "or within 2 km of the river)", **med}
    return {"threshold_db": round(otsu_threshold(hh_db), 2), "method": "Otsu (fallback: no valley, too few samples)"}


def remove_small(mask: np.ndarray, min_pixels: int) -> np.ndarray:
    if min_pixels <= 1:
        return mask
    labels, n = ndimage.label(mask)
    if n == 0:
        return mask
    sizes = ndimage.sum(mask, labels, range(1, n + 1))
    return np.isin(labels, np.flatnonzero(sizes >= min_pixels) + 1)


def classify(hh_db, hv_db, thresh_db: float, pixel_m: float, min_area_m2: float = 2000.0) -> dict:
    valid = np.isfinite(hh_db)
    smooth = ndimage.median_filter(np.nan_to_num(hh_db, nan=0.0), size=3)        # speckle
    smooth = np.where(valid, smooth, np.nan)
    water = remove_small(np.nan_to_num(smooth, nan=99) < thresh_db, int(min_area_m2 / pixel_m ** 2))
    out = {"open_water": water, "valid": valid, "unknown_pct": round(float((~valid).mean() * 100), 1),
           "hh_smooth": smooth}
    if hv_db is not None:
        hv = np.where(hv_db > HV_NOISE_FLOOR_DB, hv_db, np.nan)
        ratio = smooth - hv
        # static double-bounce candidates; change() adds the HH-rise condition
        out["flooded_veg"] = ((np.nan_to_num(smooth, nan=-99) > FV_HH_MIN_DB)
                              & (np.nan_to_num(ratio, nan=0) > FV_HH_HV_MIN_DB) & ~water)
    return out


def main_channel(water: np.ndarray, permanent_water: np.ndarray) -> np.ndarray:
    """The 8-connected water body that overlaps the permanent river mask most (else the largest)."""
    lab, n = ndimage.label(water, structure=EIGHT)
    if n == 0:
        return np.zeros_like(water)
    counts = np.bincount(lab[permanent_water], minlength=n + 1) if permanent_water.any() else np.zeros(n + 1, int)
    counts[0] = 0
    if counts.max() == 0:
        counts = np.bincount(lab.ravel(), minlength=n + 1); counts[0] = 0
    return lab == int(np.argmax(counts))


def land_parts(water: np.ndarray, valid: np.ndarray, pixel_m: float) -> tuple[np.ndarray, np.ndarray]:
    """(mainland, char) land masks. Water specks < WATER_SPECK_HA removed and a 3x3 closing applied first;
    land components (4-connected) touching the west or east edge of the AOI are mainland, the rest are chars."""
    w = remove_small(water, int(np.ceil(WATER_SPECK_HA * 1e4 / pixel_m ** 2)))
    w = ndimage.binary_closing(w, structure=EIGHT)
    land = ~w & valid
    lab, _ = ndimage.label(land)
    edge = np.setdiff1d(np.union1d(lab[:, 0], lab[:, -1]), [0])
    mainland = np.isin(lab, edge)
    return mainland, land & ~mainland


def change(before: dict, after: dict, pixel_m: float, threshold: float,
           permanent_water: np.ndarray | None = None, confirm: dict | None = None, erosion: bool = True) -> dict:
    """Same-track pair. before/after/confirm = {'hh':..., 'hv':...} on one grid.

    confirm: a pass AFTER `after` (same track). If given, erosion = N2O in both after and confirm.
    Returns areas at threshold -1/0/+1 dB plus the middle masks.
    """
    perm = np.zeros_like(before["hh"], bool) if permanent_water is None else permanent_water
    pa_km2 = pixel_m ** 2 / 1e6
    hv_ok = before.get("hv") is not None and after.get("hv") is not None
    res = {"new_water_km2": [], "receded_km2": [], "flooded_veg_km2": [], "bank_loss_ha": [],
           "char_change_ha": [], "other_new_water_km2": [], "dropped_ha": []}
    mid, by_t, dropped_sites = None, [], 0
    for d in (-1.0, 0.0, 1.0):
        t = threshold + d
        b = classify(before["hh"], before.get("hv"), t, pixel_m)
        a = classify(after["hh"], after.get("hv"), t, pixel_m)
        both = b["valid"] & a["valid"]
        n2o = a["open_water"] & ~b["open_water"] & both
        o2n = b["open_water"] & ~a["open_water"] & both
        mainland_b, char_b = land_parts(b["open_water"], b["valid"], pixel_m)
        mainland_a, char_a = land_parts(a["open_water"], a["valid"], pixel_m)
        main_a = main_b = None
        if erosion:
            main_a = main_channel(a["open_water"], perm)
            main_b = main_channel(b["open_water"], perm)
            bankline = mainland_b & ndimage.binary_dilation(main_b, structure=EIGHT)
            dist_bank = (ndimage.distance_transform_edt(~bankline) * pixel_m).astype("float32") if bankline.any() \
                else np.full(n2o.shape, np.inf, "float32")
            near = dist_bank <= BANK_LOSS_MAX_RETREAT_M
            eroded = mainland_b & main_a & near & both
            if confirm is not None:
                eroded &= classify(confirm["hh"], confirm.get("hv"), t, pixel_m)["open_water"]
            eroded = remove_small(eroded, 2)        # a shift counts only at >= 2 pixels
            # bankline-touch rule: keep only components within 1 px (8-conn) of the before mainland bankline;
            # interior patches (flooded fields, ponds reached through water) go to other_new_water
            lab, nlab = ndimage.label(eroded, structure=EIGHT)
            touch = np.unique(lab[ndimage.binary_dilation(bankline, structure=EIGHT) & eroded]) if nlab else []
            kept = np.isin(lab, [v for v in touch if v]) if nlab else eroded
            res["dropped_ha"].append(float((eroded & ~kept).sum()) * pa_km2 * 100)
            if d == 0.0:
                sz = np.bincount(lab.ravel(), minlength=nlab + 1)[1:] if nlab else np.zeros(0)
                keep_ids = set(int(v) for v in touch if v)
                dropped_sites = int(sum(1 for i, s_ in enumerate(sz, 1) if i not in keep_ids and s_ * pa_km2 * 100 >= 0.5))
            eroded = kept
        else:
            eroded = np.zeros_like(n2o); dist_bank = None
        other = n2o & ~eroded & ~char_b
        fv = None
        if hv_ok and a.get("flooded_veg") is not None:
            rise = np.nan_to_num(a["hh_smooth"] - b["hh_smooth"], nan=-99)
            fv = a["flooded_veg"] & (rise >= FV_HH_RISE_MIN_DB) & both
            res["flooded_veg_km2"].append(float(fv.sum()) * pa_km2)
        res["new_water_km2"].append(float(n2o.sum()) * pa_km2)
        res["receded_km2"].append(float(o2n.sum()) * pa_km2)
        res["bank_loss_ha"].append(float(eroded.sum()) * pa_km2 * 100)
        res["char_change_ha"].append(float(char_b.sum() - char_a.sum()) * pa_km2 * 100)
        res["other_new_water_km2"].append(float(other.sum()) * pa_km2)
        by_t.append({"n2o": n2o, "eroded": eroded, "flooded_veg": fv, "char_before": char_b, "char_after": char_a,
                     "other_new_water": other})
        if d == 0.0:
            mid = {"before_water": b["open_water"], "after_water": a["open_water"], "n2o": n2o, "o2n": o2n,
                   "eroded": eroded, "flooded_veg": fv, "char_lost": char_b & ~char_a, "char_gained": char_a & ~char_b,
                   "bank_dist_m": dist_bank, "mainland_before": mainland_b, "mainland_after": mainland_a,
                   "main_before": main_b, "main_after": main_a,
                   "unknown_pct": max(b["unknown_pct"], a["unknown_pct"])}
    rng = lambda v: [round(min(v), 3), round(max(v), 3)] if v else None   # noqa: E731
    if not erosion:
        rule = "not computed for this pair (flood pair)"
    else:
        rule = (f"mainland land in before (land component touching the AOI west/east edge, water specks < "
                f"{WATER_SPECK_HA} ha removed + 3x3 closing) that is water in after"
                + (" AND confirm pass" if confirm is not None else " (single pass: UNCONFIRMED)")
                + f", 8-connected to the main channel in after, within {BANK_LOSS_MAX_RETREAT_M} m of the before "
                  "mainland bankline, >= 2 px; each component must touch (within 1 px, 8-conn) the before mainland "
                  "bankline, otherwise it is counted as other new water")
    bl = rng(res["bank_loss_ha"])
    return {
        "threshold_db": threshold, "threshold_tested_db": [threshold - 1, threshold, threshold + 1],
        "new_water_km2_range": rng(res["new_water_km2"]), "new_water_km2_mid": round(res["new_water_km2"][1], 3),
        "receded_km2_range": rng(res["receded_km2"]),
        "mainland_bank_loss_ha_range": bl, "mainland_bank_loss_ha_mid": round(res["bank_loss_ha"][1], 3),
        "bank_loss_rule": rule, "bank_loss_confirmed": bool(erosion and confirm is not None),
        "erosion_ha_range": bl,                       # DEPRECATED alias of mainland_bank_loss_ha_range
        "erosion_rule": rule,                         # DEPRECATED alias of bank_loss_rule
        "bank_loss_dropped_not_touching_bankline_ha_range": rng(res["dropped_ha"]) if erosion else None,
        "bank_loss_dropped_sites_ge_0_5ha": dropped_sites if erosion else None,
        "char_area_change_ha_range": rng(res["char_change_ha"]),
        "char_change_reliable": False,
        "char_change_unreliable_reason": ("at T +/- 1 dB narrow water channels open or close, so chars join or split "
                                          "from the mainland and the char area can swing from gain to loss; seasonal "
                                          "submergence also counts. Shown as an overlay only, not a headline number."),
        "char_area_change_rule": "char land before minus char land after (char = land component not touching the "
                                 "AOI west/east edge); positive = char land lost",
        "other_new_water_km2_range": rng(res["other_new_water_km2"]),
        "other_new_water_rule": "new water that is neither mainland bank loss nor on before-char land",
        "flooded_vegetation_km2_range": rng(res["flooded_veg_km2"]) if hv_ok else None,
        "flooded_vegetation_rule": (f"EXPERIMENTAL: not open water in after AND HH_after > {FV_HH_MIN_DB} dB AND "
                                    f"HH_after - HV_after > {FV_HH_HV_MIN_DB} dB AND HH_after - HH_before >= "
                                    f"{FV_HH_RISE_MIN_DB} dB" if hv_ok else
                                    "not computed: HV missing in before or after pass"),
        "unknown_pixel_pct": mid["unknown_pct"], "masks": mid, "masks_by_threshold": by_t,
    }
