"""What stood on the land the river took. Deterministic: SAR change masks x land cover x building footprints.

Inputs (all optional except the masks; missing ones are reported as null with a reason):
  cache/landcover/<aoi>/worldcover.tif   ESA WorldCover 2021 v200 on the analysis grid  <- worldcover()
  cache/vector/buildings_<aoi>.csv       building centroids lon,lat,area_m2,confidence  (+ polygons geojson)
Outputs per erosion pair (written by run_aoi):
  outputs/<aoi>/pairs/<pair>_sites.geojson       mainland bank-loss sites S01.. (largest first)
  outputs/<aoi>/pairs/<pair>_char_sites.geojson  char (island) land lost, C01..  -- never called erosion
  pair JSON key `exposure` with AOI totals + caveat
"""
from __future__ import annotations

import csv
import json
import pathlib

import numpy as np
import rasterio
from rasterio import features
from rasterio.warp import Resampling, reproject, transform as warp_xy, transform_geom
from scipy import ndimage

from src.config import CACHE, VECTOR, aoi_dir

WORLDCOVER_URL = ("https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
                  "ESA_WorldCover_10m_2021_v200_N24E087_Map.tif")
WC_CLASSES = {10: "tree", 20: "shrub", 30: "grass", 40: "cropland", 50: "built_up", 60: "bare",
              70: "snow", 80: "water_2021", 90: "wetland_2021", 95: "mangrove", 100: "moss"}
# every class present in Bangladesh gets its own row; "other" only for no-data / rare classes
WC_REPORT = ["cropland", "built_up", "tree", "grass", "shrub", "bare", "water_2021", "wetland_2021", "other"]
WC_LABELS = {"cropland": "cropland", "built_up": "built-up (houses, roads)", "tree": "trees / homestead groves",
             "grass": "grass", "shrub": "shrub", "bare": "bare sand / soil", "water_2021": "already water in 2021",
             "wetland_2021": "wetland in 2021", "other": "no data / other"}
MIN_SITE_HA = 0.5
CAVEAT = ("Land cover is WorldCover 2021 and buildings are model-detected footprints from older imagery: they describe "
          "what stood there before, not a verified damage count. River stage differs between dates.")
EIGHT = np.ones((3, 3), bool)


def worldcover_path(aoi):
    return CACHE / "landcover" / aoi / "worldcover.tif"


def worldcover(aoi: str, prof: dict) -> np.ndarray | None:
    """WorldCover classes on the analysis grid (nearest). Reads only the needed blocks of the public COG."""
    out = worldcover_path(aoi)
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        dst = np.zeros((prof["height"], prof["width"]), dtype="uint8")
        try:
            with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif"):
                with rasterio.open("/vsicurl/" + WORLDCOVER_URL) as s:
                    reproject(rasterio.band(s, 1), dst, dst_transform=prof["transform"], dst_crs=prof["crs"],
                              resampling=Resampling.nearest, src_nodata=0, dst_nodata=0)
        except Exception as exc:
            print(f"[exposure] WorldCover not available ({exc!r})")
            return None
        p = dict(prof, count=1, dtype="uint8", nodata=0, compress="deflate", tiled=True)
        with rasterio.open(out, "w", **p) as d:
            d.write(dst, 1)
        (out.parent / "worldcover_receipt.json").write_text(json.dumps({
            "source": "ESA WorldCover 10 m 2021 v200 (Sentinel-1 + Sentinel-2), CC BY 4.0",
            "url": WORLDCOVER_URL, "resampling": "nearest to the analysis grid", "classes": WC_CLASSES}, indent=1))
        print(f"[exposure] WorldCover -> {out}")
    with rasterio.open(out) as s:
        return s.read(1)


def load_buildings(aoi: str):
    """Building centroids (lon, lat, area_m2) + source receipt, or (None, reason)."""
    path = VECTOR / f"buildings_{aoi}.csv"
    rc = VECTOR / f"buildings_{aoi}_receipt.json"
    if not path.exists():
        return None, "building footprints not downloaded yet"
    lon, lat, area = [], [], []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            lon.append(float(r["lon"])); lat.append(float(r["lat"])); area.append(float(r["area_m2"]))
    receipt = json.loads(rc.read_text()) if rc.exists() else {}
    return {"lon": np.array(lon), "lat": np.array(lat), "area": np.array(area), "receipt": receipt}, None


def _building_pixels(b, prof):
    xs, ys = warp_xy("EPSG:4326", prof["crs"], b["lon"].tolist(), b["lat"].tolist())
    inv = ~prof["transform"]
    cols, rows = inv * (np.asarray(xs), np.asarray(ys))
    r, c = np.floor(rows).astype(int), np.floor(cols).astype(int)
    ok = (r >= 0) & (r < prof["height"]) & (c >= 0) & (c < prof["width"])
    return r, c, ok


def _cover_ha(wc, sel, pa_ha):
    if wc is None:
        return None
    vals = wc[sel]
    out = {k: 0.0 for k in WC_REPORT}
    for code, n in zip(*np.unique(vals, return_counts=True)):
        name = WC_CLASSES.get(int(code), "other")
        out[name if name in out else "other"] += float(n) * pa_ha
    tot = sum(out.values())
    return {"ha": {k: round(v, 2) for k, v in out.items()},
            "pct": {k: round(100 * v / tot, 1) if tot else 0.0 for k, v in out.items()}, "labels": WC_LABELS}


def sites(mask, prof, prefix, wc, bld, bdist=None, extra=None, union_lookup=None):
    """Vectorise a change mask into sites (8-connected, >= MIN_SITE_HA), largest first. Returns (geojson, totals)."""
    px = prof["transform"].a; pa_ha = px * px / 1e4
    lab, n = ndimage.label(mask, structure=EIGHT)
    if n:
        sizes = np.bincount(lab.ravel(), minlength=n + 1); sizes[0] = 0
        keep = np.flatnonzero(sizes * pa_ha >= MIN_SITE_HA)
        order = keep[np.argsort(-sizes[keep], kind="stable")]
    else:
        sizes, order = np.zeros(1, int), np.array([], int)
    newlab = np.zeros(n + 1, dtype="int32"); newlab[order] = np.arange(1, len(order) + 1)
    lab2 = newlab[lab]
    if bld is not None:
        br, bc, bok = _building_pixels(bld, prof)
        bsite = np.zeros(bld["lon"].shape, "int32"); bsite[bok] = lab2[br[bok], bc[bok]]
    geoms = {i: [] for i in range(1, len(order) + 1)}
    for g, v in features.shapes(lab2, mask=lab2 > 0, transform=prof["transform"]):
        geoms[int(v)].append(g["coordinates"])
    feats = []
    tot = {"sites": len(order), "area_ha": 0.0, "buildings": 0 if bld is not None else None,
           "building_area_m2": 0.0 if bld is not None else None}
    objs = ndimage.find_objects(lab2)
    for i in range(1, len(order) + 1):
        sl = objs[i - 1]
        sel = lab2[sl] == i                                   # work on the site's bounding box only
        rr, cc = np.nonzero(sel)
        rows, cols = rr + sl[0].start, cc + sl[1].start
        cx, cy = prof["transform"] * (cols.mean() + 0.5, rows.mean() + 0.5)
        c = transform_geom(prof["crs"], "EPSG:4326", {"type": "Point", "coordinates": [cx, cy]})
        area = float(sel.sum()) * pa_ha
        props = {"site_id": f"{prefix}{i:02d}", "area_ha": round(area, 2),
                 "lat": round(c["coordinates"][1], 5), "lon": round(c["coordinates"][0], 5),
                 "land_cover": _cover_ha(wc[sl] if wc is not None else None, sel, pa_ha), **(extra or {})}
        if bdist is not None:
            props["max_retreat_m"] = round(float(np.max(bdist[sl][sel])))
        if bld is not None:
            inb = bsite == i
            props["building_count"] = int(inb.sum()); props["building_area_m2"] = round(float(bld["area"][inb].sum()), 1)
            tot["buildings"] += props["building_count"]; tot["building_area_m2"] += props["building_area_m2"]
        else:
            props["building_count"] = None
        if union_lookup is not None:
            props["union"], props["upazila"] = union_lookup(rows, cols)
        geom = transform_geom(prof["crs"], "EPSG:4326", {"type": "MultiPolygon", "coordinates": geoms[i]}, precision=6)
        feats.append({"type": "Feature", "properties": props, "geometry": geom})
        tot["area_ha"] += area
    tot["area_ha"] = round(tot["area_ha"], 2)
    tot["land_cover"] = _cover_ha(wc, lab2 > 0, pa_ha)
    if tot["building_area_m2"] is not None:
        tot["building_area_m2"] = round(tot["building_area_m2"], 1)
    return {"type": "FeatureCollection", "features": feats}, tot, lab2


def buildings_near(bld_geojson_path: pathlib.Path, site_mask, prof, out_path, buffer_m=300):
    """Clip the building polygons to within buffer_m of the sites, so the web layer stays small."""
    if not bld_geojson_path.exists():
        return 0
    px = prof["transform"].a
    near = ndimage.binary_dilation(site_mask, structure=EIGHT, iterations=max(1, int(buffer_m / px)))
    key = (str(bld_geojson_path), bld_geojson_path.stat().st_mtime)
    if _BLD_CACHE.get("key") != key:                       # parse the big file once per process
        gj = json.loads(bld_geojson_path.read_text(encoding="utf-8"))
        lon = np.array([f["properties"]["lon"] for f in gj["features"]]); lat = np.array([f["properties"]["lat"] for f in gj["features"]])
        r, c, ok = _building_pixels({"lon": lon, "lat": lat}, prof)
        _BLD_CACHE.update(key=key, feats=gj["features"], r=r, c=c, ok=ok)
    B = _BLD_CACHE
    keep = np.zeros(B["r"].shape, bool); keep[B["ok"]] = near[B["r"][B["ok"]], B["c"][B["ok"]]]
    out_path.write_text(json.dumps({"type": "FeatureCollection",
                                    "features": [B["feats"][i] for i in np.flatnonzero(keep)]}))
    return int(keep.sum())


_BLD_CACHE: dict = {}


def union_lookup_factory(prof):
    path = VECTOR / "unions.geojson"
    if not path.exists():
        return None
    gj = json.loads(path.read_text(encoding="utf-8"))
    lab = np.zeros((prof["height"], prof["width"]), "int32"); names = [None]
    for i, f in enumerate(gj["features"], 1):
        g = transform_geom("EPSG:4326", prof["crs"], f["geometry"])
        lab[features.geometry_mask([g], lab.shape, prof["transform"], invert=True)] = i
        pr = f.get("properties", {})
        names.append((pr.get("shapeName") or pr.get("name"), pr.get("upazila")))

    def look(rows, cols):
        v = np.bincount(lab[rows, cols]); v[0] = 0
        return names[int(np.argmax(v))] if v.any() else (None, None)
    return look


def _simplify(pts, tol):
    """Douglas-Peucker on a list of (x, y)."""
    if len(pts) < 3:
        return pts
    keep = np.zeros(len(pts), bool); keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    a = np.asarray(pts, float)
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        p, q = a[i], a[j]; d = q - p; L = np.hypot(*d)
        seg = a[i + 1:j]
        dist = np.abs(np.cross(d, seg - p)) / L if L else np.hypot(*(seg - p).T)
        k = int(np.argmax(dist))
        if dist[k] > tol:
            keep[i + 1 + k] = True; stack += [(i, i + 1 + k), (i + 1 + k, j)]
    return [pts[k] for k in np.flatnonzero(keep)]


def bankline(mainland, channel, prof, tol_m=20.0, min_len_m=200.0):
    """Edges of the mainland mask that face the main channel, as simplified UTM lines."""
    if mainland is None or channel is None:
        return []
    px = prof["transform"].a
    face = ndimage.binary_dilation(channel, structure=EIGHT)
    inv = ~prof["transform"]
    H, W = mainland.shape
    lines = []
    for geom, _ in features.shapes(mainland.astype("uint8"), mask=mainland, transform=prof["transform"]):
        for ring in geom["coordinates"]:
            run = []
            for (x0, y0), (x1, y1) in zip(ring[:-1], ring[1:]):
                mx, my = (x0 + x1) / 2, (y0 + y1) / 2
                nx, ny = (y1 - y0), -(x1 - x0)                     # perpendicular
                n = np.hypot(nx, ny) or 1.0
                ok = False
                for sgn in (1, -1):
                    c, r = inv * (mx + sgn * nx / n * px / 2, my + sgn * ny / n * px / 2)
                    r, c = int(np.floor(r)), int(np.floor(c))
                    if 0 <= r < H and 0 <= c < W and not mainland[r, c] and face[r, c]:
                        ok = True; break
                if ok:
                    if not run:
                        run = [(x0, y0)]
                    run.append((x1, y1))
                elif run:
                    lines.append(run); run = []
            if run:
                lines.append(run)
    out = []
    for ln in lines:
        if len(ln) * px * 0.5 < min_len_m and np.hypot(ln[-1][0] - ln[0][0], ln[-1][1] - ln[0][1]) < min_len_m:
            continue
        out.append(_simplify(ln, tol_m))
    return out


def banklines_geojson(masks, pr, prof):
    feats = []
    for side, date, mk, ch in (("before", pr["before"], "mainland_before", "main_before"),
                               ("after", pr["after"], "mainland_after", "main_after")):
        for ln in bankline(masks.get(mk), masks.get(ch), prof):
            g = transform_geom(prof["crs"], "EPSG:4326", {"type": "LineString", "coordinates": ln}, precision=6)
            feats.append({"type": "Feature", "properties": {"side": side, "date": date,
                          "label": f"River bank, {int(date[6:])} {['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][int(date[4:6]) - 1]} {date[:4]}"},
                          "geometry": g})
    return {"type": "FeatureCollection", "features": feats}


def _png(path, rgb):
    with rasterio.open(path, "w", driver="PNG", height=rgb.shape[0], width=rgb.shape[1], count=3, dtype="uint8") as d:
        d.write(np.moveaxis(rgb, -1, 0))


def site_chips(lab, before, after, masks, out_dir, n=20, pad_m=400, scale=3, prof=None):
    """Per top-n site: greyscale HH (-25..0 dB) before/after, water tinted blue, site outline in yellow."""
    out_dir.mkdir(parents=True, exist_ok=True)
    px = prof["transform"].a
    pad = int(pad_m / px)
    objs = ndimage.find_objects(lab)
    files = {}
    for i, sl in enumerate(objs[:n], 1):
        if sl is None:
            continue
        r0, r1 = max(0, sl[0].start - pad), min(lab.shape[0], sl[0].stop + pad)
        c0, c1 = max(0, sl[1].start - pad), min(lab.shape[1], sl[1].stop + pad)
        site = lab[r0:r1, c0:c1] == i
        edge = site & ~ndimage.binary_erosion(site, structure=EIGHT)
        for side, sar, water in (("before", before["hh"], masks["before_water"]), ("after", after["hh"], masks["after_water"])):
            g = np.clip((np.nan_to_num(sar[r0:r1, c0:c1], nan=-25) + 25) / 25, 0, 1) * 255
            rgb = np.dstack([g, g, g])
            w = water[r0:r1, c0:c1]
            rgb[w] = rgb[w] * 0.35 + np.array([30, 120, 255]) * 0.65
            rgb = np.kron(rgb, np.ones((scale, scale, 1)))
            e = ndimage.binary_dilation(np.kron(edge, np.ones((scale, scale))).astype(bool), iterations=1)
            rgb[e] = [255, 235, 0]
            name = f"S{i:02d}_{side}.png"
            _png(out_dir / name, rgb.clip(0, 255).astype("uint8"))
            files.setdefault(f"S{i:02d}", {})[side] = name
    return files


def pair_exposure(aoi, prof, pr, info, masks, od, before=None, after=None) -> dict:
    """Sites + totals for one erosion pair. Writes the two site files, returns the `exposure` block."""
    wc = worldcover(aoi, prof)
    bld, bld_reason = load_buildings(aoi)
    look = union_lookup_factory(prof)
    extra = {"pair": pr["id"], "before": pr["before"], "after": pr["after"], "confirm": info.get("confirm_pass"),
             "confirmed": bool(info.get("bank_loss_confirmed")), "kind": "mainland_bank_loss"}
    gj, tot, lab = sites(masks["eroded"], prof, "S", wc, bld, masks.get("bank_dist_m"), extra, look)
    (od / "pairs" / f"{pr['id']}_sites.geojson").write_text(json.dumps(gj))
    cextra = {**extra, "kind": "char_land_lost", "confirmed": None}
    cgj, ctot, _ = sites(masks["char_lost"], prof, "C", wc, bld, None, cextra, look)
    (od / "pairs" / f"{pr['id']}_char_sites.geojson").write_text(json.dumps(cgj))
    nb = buildings_near(VECTOR / f"buildings_{aoi}.geojson", lab > 0, prof, od / "pairs" / f"{pr['id']}_buildings.geojson")
    (od / "pairs" / f"{pr['id']}_banklines.geojson").write_text(json.dumps(banklines_geojson(masks, pr, prof)))
    # mean InSAR coherence over each site, for the 12-day GUNW pairs inside [before, after] (observation only)
    coh_files = sorted(f for f in (CACHE / "coherence" / aoi).glob(f"coh_{pr['track']}_*.tif")
                       if pr["before"] <= f.stem.split("_")[2] and f.stem.split("_")[3] <= pr["after"])
    if coh_files:
        from src.pipeline.run_aoi import to_grid
        stack = np.nanmean(np.stack([to_grid(f, prof) for f in coh_files]), axis=0)
        objs = ndimage.find_objects(lab)
        for f in gj["features"]:
            i = int(f["properties"]["site_id"][1:]); sl = objs[i - 1]
            v = stack[sl][lab[sl] == i]
            f["properties"]["mean_coherence"] = round(float(np.nanmean(v)), 2) if np.isfinite(v).any() else None
            f["properties"]["coherence_pairs"] = [x.stem[9:] for x in coh_files]
        (od / "pairs" / f"{pr['id']}_sites.geojson").write_text(json.dumps(gj))
    chips = {}
    if before is not None and after is not None:
        chips = site_chips(lab, before, after, masks, od / "sites" / pr["id"], prof=prof)
        for f in gj["features"]:
            c = chips.get(f["properties"]["site_id"])
            if c:
                f["properties"]["chips"] = {k: f"sites/{pr['id']}/{v}" for k, v in c.items()}
        (od / "pairs" / f"{pr['id']}_sites.geojson").write_text(json.dumps(gj))
    wrc = worldcover_path(aoi).parent / "worldcover_receipt.json"
    return {
        "mainland_bank_loss": {**tot, "area_ha_range": info.get("mainland_bank_loss_ha_range")},
        "char_land_lost": ctot,
        "buildings_source": bld["receipt"] if bld is not None else None,
        "buildings_note": bld_reason, "buildings_near_sites_written": nb,
        "land_cover_source": json.loads(wrc.read_text())["source"] if wrc.exists() else None,
        "min_site_ha": MIN_SITE_HA, "files": {"sites": f"pairs/{pr['id']}_sites.geojson",
                                              "char_sites": f"pairs/{pr['id']}_char_sites.geojson",
                                              "buildings": f"pairs/{pr['id']}_buildings.geojson" if nb else None,
                                              "banklines": f"pairs/{pr['id']}_banklines.geojson"},
        "caveat": CAVEAT,
    }
