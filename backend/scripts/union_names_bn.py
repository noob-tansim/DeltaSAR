"""Bangla names for every union in the reach, from the open Bangladesh geocode dataset (BBS names, MIT licence:
github.com/nuhil/bangladesh-geocode), matched within the same upazila by spelling and by distance between centres.

    python scripts/union_names_bn.py --geocode <folder with districts.json, upazilas.json, unions.json> [--write]

Names from the team's copy sheet win. A union is matched only when the spellings agree closely, or agree fairly and
the two centres are within 6 km; anything else keeps its English name and is listed for the native-reader review.
A name with no match in its upazila may match the same name within 5 km in a neighbouring one (boundaries differ
between sources). Municipalities ("<town> Paurashava") get "<town in Bangla> পৌরসভা". Upazila names are stored as "upazila:<English>".
"""
from __future__ import annotations

import argparse
import difflib
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAMES = ROOT / "data" / "union_names_bn.json"
UNIONS = ROOT / "deploy_data" / "kazipur" / "union_summary.json"
DISTRICTS = {"Sirajganj", "Bogura", "Tangail", "Jamalpur", "Pabna", "Gaibandha", "Natore", "Sherpur", "Mymensingh"}
FOLDS = [("ph", "f"), ("bh", "b"), ("dh", "d"), ("th", "t"), ("kh", "k"), ("gh", "g"), ("chh", "c"), ("ch", "c"),
         ("sh", "s"), ("jh", "j"), ("oo", "u"), ("ee", "i"), ("ou", "o"), ("w", "o"), ("y", "i"), ("z", "j"), ("aa", "a")]


def norm(s: str) -> str:
    s = re.sub(r"\b(union|sadar|paurashava|pourashava|municipality)\b", "", s.lower())
    s = re.sub(r"[^a-z]", "", s)
    for a, b in FOLDS:
        s = s.replace(a, b)
    return re.sub(r"(.)\1+", r"\1", s)            # double letters: "Ullah Para" ~ "Ullapara"


def ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


def km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p = math.pi / 180
    h = math.sin((lat2 - lat1) * p / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))


def table(folder: Path, name: str) -> list[dict]:
    j = json.loads((folder / f"{name}.json").read_text(encoding="utf-8"))
    return next(x for x in j if x.get("type") == "table")["data"]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--geocode", required=True, type=Path)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    team = json.loads(NAMES.read_text(encoding="utf-8"))
    ours = json.loads(UNIONS.read_text(encoding="utf-8"))
    dist = {d["id"]: d for d in table(a.geocode, "districts")}
    upas = [u for u in table(a.geocode, "upazilas") if dist[u["district_id"]]["name"] in DISTRICTS]
    gunions = table(a.geocode, "unions")

    out: dict[str, str] = {"_note": "", "_source": ""}
    upa_map: dict[str, dict] = {}
    for en in sorted({u["upazila_name_en"] for u in ours if u.get("upazila_name_en")}):
        best = max(upas, key=lambda g: ratio(en, g["name"]))
        r = ratio(en, best["name"])
        if r >= 0.75:
            upa_map[en] = best
            out[f"upazila:{en}"] = best["bn_name"]
        print(f"upazila {en:18s} -> {best['name']:18s} {best['bn_name']:14s} {r:.2f} {'OK' if r >= 0.75 else 'NO'}")

    matched, team_n, unmatched = 0, 0, []
    for u in ours:
        en, upa = u["union_name_en"], u.get("upazila_name_en")
        if en in team and not en.startswith("_"):
            out[en] = team[en]
            team_n += 1
            continue
        g_upa = upa_map.get(upa)
        if en.lower().endswith("paurashava"):
            town = en[: -len("paurashava")].strip()
            if g_upa and ratio(town, g_upa["name"]) >= 0.75:
                out[en] = f"{g_upa['bn_name'].removesuffix(' সদর')} পৌরসভা"
                matched += 1
                print(f"  {en:26s} -> {out[en]} (municipality)")
                continue
            unmatched.append(f"{en} ({upa})")
            continue
        cands = [g for g in gunions if g_upa and g["upazilla_id"] == g_upa["id"]]
        c = u["coordinates"]

        def score(g: dict) -> tuple[float, float]:
            d = km(c["lat"], c["lon"], float(g["lat"]), float(g["lon"])) if g.get("lat") and g.get("lon") else 99.0
            return ratio(en, g["name"]), d
        ranked = sorted(cands, key=lambda g: -score(g)[0])
        g = ranked[0] if ranked else None
        r, d = score(g) if g else (0.0, 99.0)
        ok = r >= 0.8 or (r >= 0.6 and d <= 6)
        if not ok:      # boundaries differ between sources: the same name within 5 km in a neighbouring upazila
            near = [x for x in gunions if x.get("lat") and x.get("lon") and score(x)[0] >= 0.9 and score(x)[1] <= 5]
            if near:
                g = near[0]
                r, d = score(g)
                ok = True
        if g is None:
            unmatched.append(f"{en} ({upa})")
            continue
        print(f"  {en:26s} -> {g['name']:22s} {g['bn_name']:16s} name {r:.2f} dist {d:5.1f} km {'OK' if ok else 'NO'}")
        if ok:
            out[en] = g["bn_name"]
            matched += 1
        else:
            unmatched.append(f"{en} ({upa})")
    out["_note"] = ("Bangla names for the unions in union_summary.json, keyed by English name; 'upazila:<English>' for "
                    f"upazilas. {team_n} from the team's copy sheet, {matched} matched from the Bangladesh geocode "
                    "dataset (BBS names) by scripts/union_names_bn.py. Bangla text stays a draft until a native reader checks it.")
    out["_source"] = "github.com/nuhil/bangladesh-geocode (MIT licence), districts/upazilas/unions tables"
    out["_unmatched"] = "; ".join(unmatched)
    print(f"\nteam {team_n}, matched {matched}, English only {len(unmatched)}: {out['_unmatched']}")
    if a.write:
        NAMES.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print("wrote", NAMES)


if __name__ == "__main__":
    main()
