"""Opciones finales para "mente" en contexto real (tinta, tamano real + zoom 2x).

A) Cormorant Garamond 500 (actual)
B) Nanum Myeongjo 400 (mejor 'e' del bake-off)
C) Libre Baskerville 400 (mejor word-IoU)
D) Franken: CG500 para m/n/t + NM400 para las 'e'
"""
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
INK = "#86b0a3"

regions = json.load(open(BOXES, encoding="utf-8"))
mente = next(r for r in regions if r["text"] == "mente")
gboxes = mente["glyph_boxes"]
X0, Y0, X1, Y1 = mente["bbox"]
PAD = 12
vx0, vy0 = X0 - PAD, Y0 - PAD
vw, vh = (X1 - X0) + 2 * PAD, (Y1 - Y0) + 2 * PAD

orig = cv2.imread(ORIG)
crop_o = orig[vy0:vy0 + vh, vx0:vx0 + vw]

_font_cache = {}


def get_font(name):
    if name not in _font_cache:
        f = TTFont(str(CACHE / f"{name}.ttf"))
        _font_cache[name] = (f.getGlyphSet(), f.getBestCmap())
    return _font_cache[name]


def glyph_info(fontname, ch):
    glyph_set, cmap = get_font(fontname)
    gname = cmap[ord(ch)]
    bp = BoundsPen(glyph_set)
    glyph_set[gname].draw(bp)
    pen = SVGPathPen(glyph_set)
    glyph_set[gname].draw(pen)
    return pen.getCommands(), bp.bounds


def word_render(font_per_glyph):
    """font_per_glyph: lista de 5 nombres de fuente. Escala comun POR FUENTE
    (cada fuente tiene sus unidades), calculada sobre la palabra completa."""
    scales = {}
    for fname in set(font_per_glyph):
        rs = []
        for ch, (x0, y0, x1, y1) in zip("mente", gboxes):
            _, fb = glyph_info(fname, ch)
            rs.append((y1 - y0) / (fb[3] - fb[1]))
        scales[fname] = float(np.median(rs))
    parts = []
    for ch, fname, (x0, y0, x1, y1) in zip("mente", font_per_glyph, gboxes):
        d, fb = glyph_info(fname, ch)
        s = scales[fname]
        xmin, ymin, xmax, ymax = fb
        cx = (x0 + x1) / 2.0 - vx0
        tx = cx - s * (xmin + xmax) / 2.0
        ty = (y1 - vy0) + s * ymin
        parts.append(f'<path d="{d}" transform="translate({tx:.2f} {ty:.2f}) scale({s:.5f} -{s:.5f})" />')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{vw}" height="{vh}" '
           f'viewBox="0 0 {vw} {vh}"><rect width="{vw}" height="{vh}" fill="white"/>'
           f'<g fill="{INK}">' + "".join(parts) + "</g></svg>")
    png = bytes(resvg_py.svg_to_bytes(svg_string=svg))
    arr = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED)
    a = arr[:, :, 3:4].astype(np.float32) / 255.0
    return (arr[:, :, :3].astype(np.float32) * a + 255.0 * (1 - a)).astype(np.uint8)


CG, NM, LB = "Cormorant_Garamond_500", "Nanum_Myeongjo_400", "Libre_Baskerville_400"
OPCIONES = [
    ("A) Cormorant Garamond 500 (actual)", [CG] * 5),
    ("B) Nanum Myeongjo 400", [NM] * 5),
    ("C) Libre Baskerville 400", [LB] * 5),
    ("D) CG500 + 'e' de Nanum Myeongjo", [CG, NM, CG, CG, NM]),
]

Z = 2
rows = []
for lab, fonts in [("ORIGINAL", None)] + OPCIONES:
    img = crop_o if fonts is None else word_render(fonts)
    t = cv2.resize(img, None, fx=Z, fy=Z, interpolation=cv2.INTER_NEAREST)
    bar = np.full((34, t.shape[1], 3), 255, np.uint8)
    cv2.putText(bar, lab, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2, cv2.LINE_AA)
    rows.extend([bar, t, np.zeros((4, t.shape[1], 3), np.uint8)])
out = r"C:\Users\simon\Desktop\Ale\_mente_opciones.png"
cv2.imwrite(out, np.vstack(rows[:-1]))
print("OK ->", out)
