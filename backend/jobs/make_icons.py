"""App icons for the phone app (plain mark: a radar dot over three water lines). Run once.

  python -m jobs.make_icons
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw

from src.config import ROOT

OUT = ROOT / "web" / "app" / "public" / "icons"


def icon(size: int, pad: float) -> Image.Image:
    im = Image.new("RGB", (size, size), "#9C2F6E")
    d = ImageDraw.Draw(im)
    c, r = size / 2, size * (0.5 - pad)
    for i, y in enumerate((0.52, 0.64, 0.76)):
        pts = [(x, size * y + math.sin((x - (c - r)) / (2 * r) * math.pi * 3 + i) * size * 0.035)
               for x in range(int(c - r), int(c + r) + 1, max(1, size // 128))]
        d.line(pts, fill="#FFFFFF" if i == 0 else "#F6E3EE", width=max(3, size // 28), joint="curve")
    rr = size * 0.085
    d.ellipse((c - rr, size * 0.30 - rr, c + rr, size * 0.30 + rr), fill="#3CC8F0")
    return im


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    icon(192, 0.16).save(OUT / "icon-192.png")
    icon(512, 0.16).save(OUT / "icon-512.png")
    icon(512, 0.26).save(OUT / "icon-512-maskable.png")
    print("icons written to", OUT)
