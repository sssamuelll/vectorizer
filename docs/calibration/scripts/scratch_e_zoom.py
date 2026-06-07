"""Zoom 4x + overlay de la 'e' final de "mente" para los candidatos top."""
import sys

sys.stdout.reconfigure(encoding="utf-8")

import json
from pathlib import Path

import cv2
import numpy as np
import resvg_py
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

ORIG = r"C:\Users\simon\Desktop\Ale\logo_ale.jpeg"
BOXES = r"C:\Users\simon\Desktop\Ale\_boxes.json"
CACHE = Path.home() / ".cache" / "vectorizer-fonts"

CANDIDATOS = [
    "Cormorant_Garamond_500",
    "Cormorant_Garamond_400",
    "Nanum_Myeongjo_400",
    "EB_Garamond_400",
    "EB_Garamond_500",
    "Libre_Baskerville_400",
    "Shippori_Mincho_500",
    "Newsreader_400",
    "Lora_400",
]

regions = json.load(open(BOXES, encoding="utf-8"))
mente = next(r for r in regions if r["text"] == "mente")
gboxes = mente["glyph_boxes"]
ex0, ey0, ex1, ey1 = gboxes[4]  # 'e' final
PAD = 8
vx0, vy0 = ex0 - PAD, ey0 - PAD
vw, vh = (ex1 - ex0) + 2 * PAD, (ey1 - ey0) + 2 * PAD

orig = cv2.imread(ORIG)
crop_o = orig[vy0:vy0 + vh, vx0:vx0 + vw]
g = cv2.cvtColor(crop_o, cv2.COLOR_BGR2GRAY)
_, bin_o = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)


def render_e(ttf_path):
    font = TTFont(str(ttf_path))
    glyph_set = font.getGlyphSet()
    cmap = font.getBestCmap()
    info = []
    for ch in "mente":
        gname = cmap[ord(ch)]
        bp = BoundsPen(glyph_set)
        glyph_set[gname].draw(bp)
        info.append((gname, bp.bounds))
    ratios = [(y1 - y0) / (fb[3] - fb[1])
              for (gn, fb), (x0, y0, x1, y1) in zip(info, gboxes)]
    s = float(np.median(ratios))
    gname, fb = info[4]
    pen = SVGPathPen(glyph_set)
    glyph_set[gname].draw(pen)
    d = pen.getCommands()
    xmin, ymin, xmax, ymax = fb
    cx = (ex0 + ex1) / 2.0 - vx0
    tx = cx - s * (xmin + xmax) / 2.0
    ty = (ey1 - vy0) + s * ymin
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{vw}" height="{vh}" '
           f'viewBox="0 0 {vw} {vh}"><path d="{d}" '
           f'transform="translate({tx:.2f} {ty:.2f}) scale({s:.5f} -{s:.5f})" /></svg>')
    png = bytes(resvg_py.svg_to_bytes(svg_string=svg))
    arr = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED)
    return (arr[:, :, 3] > 127).astype(np.uint8) * 255


Z = 5
tiles, labels = [], []
# original
t0 = cv2.cvtColor(255 - bin_o, cv2.COLOR_GRAY2BGR)
tiles.append(cv2.resize(t0, None, fx=Z, fy=Z, interpolation=cv2.INTER_NEAREST))
labels.append("ORIGINAL")
for cand in CANDIDATOS:
    p = CACHE / f"{cand}.ttf"
    if not p.exists():
        print("skip (no cache):", cand)
        continue
    bin_r = render_e(p)
    # overlay: original=verde, candidata=magenta, interseccion=oscuro
    ov = np.full((vh, vw, 3), 255, np.uint8)
    o, r = bin_o > 0, bin_r > 0
    ov[o & ~r] = (80, 170, 80)
    ov[r & ~o] = (200, 60, 200)
    ov[o & r] = (60, 60, 60)
    side = np.hstack([cv2.cvtColor(255 - bin_r, cv2.COLOR_GRAY2BGR),
                      np.full((vh, 4, 3), 255, np.uint8), ov])
    tiles.append(cv2.resize(side, None, fx=Z, fy=Z, interpolation=cv2.INTER_NEAREST))
    labels.append(cand.replace("_", " "))

wmax = max(t.shape[1] for t in tiles)
rows = []
for t, lab in zip(tiles, labels):
    bar = np.full((30, wmax, 3), 255, np.uint8)
    cv2.putText(bar, lab, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 1, cv2.LINE_AA)
    if t.shape[1] < wmax:
        t = np.hstack([t, np.full((t.shape[0], wmax - t.shape[1], 3), 255, np.uint8)])
    rows.extend([bar, t])
out = r"C:\Users\simon\Desktop\Ale\_e_zoom.png"
cv2.imwrite(out, np.vstack(rows))
print("OK ->", out)
