"""Make the Bangla review sheet: every Bangla sentence the app shows or speaks, next to its English, with where it lives.

    python scripts/extract_bangla.py        ->  docs/BANGLA_REVIEW.md and docs/bangla_review.csv

A native reader marks each row OK or writes the corrected Bangla in the "Correction" column; send the CSV back and the
corrections are applied to the source files.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "frontend" / "src"
BACK = ROOT / "backend" / "src" / "alerts"
BN = re.compile(r"[ঀ-৿]")
rows: list[dict[str, str]] = []

# 1. phone app strings: key: ['bangla', 'english'], // NEW
for m in re.finditer(r"^\s*(\w+): \['([^']*)', '([^']*)'\],?\s*(//\s*NEW)?", (SRC / "phone" / "strings.ts").read_text(encoding="utf-8"), re.M):
    if BN.search(m.group(2)):
        rows.append({"where": "Phone app", "id": m.group(1), "english": m.group(3), "bangla": m.group(2),
                     "status": "NEW: needs check" if m.group(4) else "from the team's copy sheet"})

# 2. website pairs: L('english', 'bangla') and simple inline T(lang, 'bangla', 'english')
pair = re.compile(r"L\(\s*'((?:[^'\\]|\\.)*)'\s*,\s*'((?:[^'\\]|\\.)*)'\s*\)", re.S)
tri = re.compile(r"T\(lang,\s*'((?:[^'\\]|\\.)*)'\s*,\s*'((?:[^'\\]|\\.)*)'\s*\)", re.S)
for f in sorted(SRC.rglob("*.tsx")):
    text = f.read_text(encoding="utf-8")
    rel = f.relative_to(ROOT / "frontend").as_posix()
    for m in pair.finditer(text):
        en, bn = m.group(1), m.group(2)
        if BN.search(bn):
            rows.append({"where": f"Website · {rel}", "id": f"line {text[:m.start()].count(chr(10)) + 1}", "english": en, "bangla": bn, "status": "NEW: needs check"})
    for m in tri.finditer(text):
        bn, en = m.group(1), m.group(2)
        if BN.search(bn):
            rows.append({"where": f"Phone app · {rel}", "id": f"line {text[:m.start()].count(chr(10)) + 1}", "english": en, "bangla": bn, "status": "NEW: needs check"})

# 3. alert messages sent to people (server templates)
for f in ("messages.py", "settings.py"):
    text = (BACK / f).read_text(encoding="utf-8")
    for m in re.finditer(r"[\"']([^\"'\n]*[ঀ-৿][^\"'\n]*)[\"']", text):
        rows.append({"where": f"Alert message · backend/src/alerts/{f}", "id": f"line {text[:m.start()].count(chr(10)) + 1}",
                     "english": "(see the English template next to it)", "bangla": m.group(1), "status": "NEW: needs check"})

# de-duplicate identical Bangla
seen, out = set(), []
for r in rows:
    k = (r["bangla"], r["where"].split(" · ")[0])
    if k not in seen:
        seen.add(k)
        out.append(r)

docs = ROOT / "docs"
with open(docs / "bangla_review.csv", "w", encoding="utf-8-sig", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["where", "id", "english", "bangla", "status", "OK? (yes/no)", "Correction"])
    w.writeheader()
    for r in out:
        w.writerow({**r, "OK? (yes/no)": "", "Correction": ""})

new = sum(r["status"].startswith("NEW") for r in out)
md = ["# Bangla review sheet", "",
      f"{len(out)} Bangla sentences, {new} of them new (not yet checked by a native reader).", "",
      "How to review: open `bangla_review.csv` in Google Sheets or Excel. For each row write **yes** in *OK?* or the corrected Bangla in *Correction*. "
      "Keep numbers and names like NISAR, FFWC, 1090 as they are. Send the file back; the corrections are applied to the code.", "",
      "Not in this sheet: the longer formatted paragraphs on the story, demo and methods pages. Read those on https://deltasar.vercel.app with the বাংলা switch (top right) and note any fixes by page.", "",
      "Rules from the team's copy sheet: calm words, no fear words, simple everyday Bangla, Bangla digits, and every alert ends with "
      "\"এটি সরকারি সতর্কবার্তা নয়\" and the 1090 line.", "",
      "| # | Where | English | Bangla | Status |", "|---|---|---|---|---|"]
for i, r in enumerate(out, 1):
    md.append(f"| {i} | {r['where']} ({r['id']}) | {r['english'][:110].replace('|', '/')} | {r['bangla'][:160].replace('|', '/')} | {r['status']} |")
(docs / "BANGLA_REVIEW.md").write_text("\n".join(md) + "\n", encoding="utf-8")
print(f"{len(out)} sentences ({new} new) -> docs/BANGLA_REVIEW.md, docs/bangla_review.csv")
