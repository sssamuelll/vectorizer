"""Bake-off de la 'e' de "mente": todas las serifs cacheadas, colocadas
glifo a glifo en posicion final, IoU exacto por glifo (sin alineacion:
la colocacion ya es la del entregable). Ranking por IoU de las 'e'.
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

import json
import re
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
WORD = "mente"
E_IDX = [1, 4]  # posiciones de las 'e'

SERIF_FAMILIES = [
    "Cormorant_Garamond", "Cormorant", "Libre_Baskerville", "Baskervville",
    "EB_Garamond", "Crimson_Pro", "Crimson_Text", "STIX_Two_Text", "Lora",
    "Spectral", "Source_Serif_4", "Playfair", "Playfair_Display",
    "Noto_Serif", "Merriweather", "Literata", "Newsreader", "Vollkorn",
    "Cardo", "Quattrocento", "Old_Standard_TT", "Libre_Caslon_Text",
    "PT_Serif", "Frank_Ruhl_Libre", "Alegreya", "Bodoni_Moda", "Domine",
    "IBM_Plex_Serif", "Prata", "Unna", "Marcellus", "Fraunces",
    "DM_Serif_Text", "Instrument_Serif", "Tinos", "Nanum_Myeongjo",
    "Shippori_Mincho", "Sawarabi_Mincho",
]

regions = json.load(open(BOXES, encoding="utf-8"))
mente = next(r for r in regions if r["text"] == "mente")
gboxes = mente["glyph_boxes"]
X0, Y0, X1, Y1 = mente["bbox"]
PAD = 10
vx0, vy0 = X0 - PAD, Y0 - PAD
vw, vh = (X1 - X0) + 2 * PAD, (Y1 - Y0) + 2 * PAD

orig = cv2.imread(ORIG)
crop_o = orig[vy0:vy0 + vh, vx0:vx0 + vw]
g = cv2.cvtColor(crop_o, cv2.COLOR_BGR2GRAY)
_, bin_o = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)


def word_svg(ttf_path):
    """SVG del crop con la palabra colocada glifo a glifo. None si falla."""
    try:
        font = TTFont(str(ttf_path))
        glyph_set = font.getGlyphSet()
        cmap = font.getBestCmap()
        info = []
        for ch in WORD:
            if ord(ch) not in cmap:
                return None
            gname = cmap[ord(ch)]
            bp = BoundsPen(glyph_set)
            glyph_set[gname].draw(bp)
            if bp.bounds is None:
                return None
            info.append((gname, bp.bounds))
    except Exception:
        return None
    ratios = [(y1 - y0) / (fb[3] - fb[1])
              for (gn, fb), (x0, y0, x1, y1) in zip(info, gboxes)
              if fb[3] - fb[1] > 0]
    s = float(np.median(ratios))
    parts = []
    for (gname, fb), (x0, y0, x1, y1) in zip(info, gboxes):
        pen = SVGPathPen(glyph_set)
        glyph_set[gname].draw(pen)
        d = pen.getCommands()
        xmin, ymin, xmax, ymax = fb
        cx = (x0 + x1) / 2.0 - vx0
        tx = cx - s * (xmin + xmax) / 2.0
        ty = (y1 - vy0) + s * ymin
        parts.append(f'<path d="{d}" transform="translate({tx:.2f} {ty:.2f}) scale({s:.5f} -{s:.5f})" />')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{vw}" height="{vh}" '
            f'viewBox="0 0 {vw} {vh}"><g fill="#000">' + "".join(parts) + "</g></svg>")


def render_bin(svg):
    png = bytes(resvg_py.svg_to_bytes(svg_string=svg))
    arr = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED)
    return (arr[:, :, 3] > 127).astype(np.uint8) * 255


def iou_box(a, b, box):
    x0, y0, x1, y1 = box
    sa = a[y0 - vy0:y1 - vy0, x0 - vx0:x1 - vx0] > 0
    sb = b[y0 - vy0:y1 - vy0, x0 - vx0:x1 - vx0] > 0
    u = (sa | sb).sum()
    return (sa & sb).sum() / u if u else 0.0


results = []
renders = {}
for fam in SERIF_FAMILIES:
    for ttf in sorted(CACHE.glob(f"{fam}_*.ttf")):
        m = re.match(rf"^{fam}_(\d+)\.ttf$", ttf.name)
        if not m:
            continue
        svg = word_svg(ttf)
        if svg is None:
            continue
        bin_r = render_bin(svg)
        ious = [iou_box(bin_o, bin_r, b) for b in gboxes]
        e_iou = float(np.mean([ious[i] for i in E_IDX]))
        word_iou = float(np.mean(ious))
        key = f"{fam.replace('_', ' ')} {m.group(1)}"
        results.append((e_iou, word_iou, key))
        renders[key] = bin_r

results.sort(reverse=True)
print(f"{'familia/peso':32s} {'e-IoU':>7s} {'word-IoU':>9s}")
cg500 = next((r for r in results if r[2] == "Cormorant Garamond 500"), None)
for e_iou, w_iou, key in results[:15]:
    mark = " <- actual" if key == "Cormorant Garamond 500" else ""
    print(f"{key:32s} {e_iou:7.3f} {w_iou:9.3f}{mark}")
if cg500 and cg500[2] not in [r[2] for r in results[:15]]:
    print(f"...\n{cg500[2]:32s} {cg500[0]:7.3f} {cg500[1]:9.3f} <- actual (pos {results.index(cg500)+1})")

# tira visual: original + top 8 + actual
top = [k for _, _, k in results[:8]]
if "Cormorant Garamond 500" not in top:
    top.append("Cormorant Garamond 500")
tiles = [cv2.resize(crop_o, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)]
labels = ["ORIGINAL"]
for k in top:
    img = cv2.cvtColor(255 - renders[k], cv2.COLOR_GRAY2BGR)
    tiles.append(cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST))
    labels.append(k)
sep = np.zeros((6, tiles[0].shape[1], 3), np.uint8)
rows = []
for t, lab in zip(tiles, labels):
    bar = np.full((28, t.shape[1], 3), 255, np.uint8)
    cv2.putText(bar, lab, (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1, cv2.LINE_AA)
    rows.extend([bar, t, sep])
out = r"C:\Users\simon\Desktop\Ale\_bakeoff_e.png"
cv2.imwrite(out, np.vstack(rows[:-1]))
print("OK ->", out)
