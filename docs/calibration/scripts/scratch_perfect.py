"""Compone el logo hibrido: caligrafia vectorizada (res nativa, winner B)
+ texto tipografico desde TTF (Cormorant Garamond 500 / STIX Two Text 600)
colocado glifo a glifo en las posiciones del original.
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2
import numpy as np
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

from vectorize import (clean_binary_mask, extract_stroke_color,
                       load_image_bgr, trace_contours)

ORIG = r"C:\Users\simon\Desktop\Ale\logo_ale.jpeg"
BOXES = r"C:\Users\simon\Desktop\Ale\_boxes.json"
OUT_SVG = r"C:\Users\simon\Desktop\Ale\logo_ale_perfecto.svg"
CACHE = Path.home() / ".cache" / "vectorizer-fonts"

FONTS = {
    "mente": (CACHE / "Cormorant_Garamond_500.ttf", "mente"),
    "INTEGRATIVE PSYCHOLOGY": (CACHE / "STIX_Two_Text_600.ttf",
                               "INTEGRATIVEPSYCHOLOGY"),
}
PAD = 6  # margen al enmascarar regiones de texto

# ── 1. caligrafia: enmascarar texto y vectorizar a res nativa (winner B) ──
img = load_image_bgr(ORIG)
h, w = img.shape[:2]
regions = json.load(open(BOXES, encoding="utf-8"))

masked = img.copy()
for r in regions:
    x0, y0, x1, y1 = r["bbox"]
    masked[max(0, y0 - PAD):min(h, y1 + PAD),
           max(0, x0 - PAD):min(w, x1 + PAD)] = 255

gray = cv2.cvtColor(masked, cv2.COLOR_BGR2GRAY)
gray = cv2.GaussianBlur(gray, (3, 3), 0)  # --blur 1
_, binary = cv2.threshold(gray, 0, 255,
                          cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE,
                          np.ones((2, 2), np.uint8), iterations=1)
binary_clean = clean_binary_mask(binary)

# winner B (--rdp 0.4 --chaikin 3) pasa a trace_contours como (0.5, 2)
caligrafia = trace_contours(binary_clean, rdp_eps=0.5, chaikin_iter=2,
                            tension=0.5)
print(f"caligrafia: {len(caligrafia)} contornos")

ink = extract_stroke_color(img, binary_clean)
print("ink:", ink)

# ── 2. texto tipografico: un path por glifo, escala comun por region ──
def region_glyph_paths(ttf_path, chars, glyph_boxes):
    font = TTFont(str(ttf_path))
    glyph_set = font.getGlyphSet()
    cmap = font.getBestCmap()

    info = []  # (char, gname, bbox_font)
    for ch in chars:
        gname = cmap[ord(ch)]
        bp = BoundsPen(glyph_set)
        glyph_set[gname].draw(bp)
        info.append((ch, gname, bp.bounds))

    # escala comun: mediana de (altura original / altura del glifo en la fuente)
    ratios = []
    for (ch, gname, fb), (x0, y0, x1, y1) in zip(info, glyph_boxes):
        fh = fb[3] - fb[1]
        if fh > 0:
            ratios.append((y1 - y0) / fh)
    s = float(np.median(ratios))
    print(f"  {ttf_path.name}: escala comun {s:.5f} ({len(ratios)} glifos)")

    out = []
    for (ch, gname, fb), (x0, y0, x1, y1) in zip(info, glyph_boxes):
        pen = SVGPathPen(glyph_set)
        glyph_set[gname].draw(pen)
        d = pen.getCommands()
        xmin, ymin, xmax, ymax = fb
        cx = (x0 + x1) / 2.0
        # centro x alineado, fondo del bbox alineado (overshoot incluido)
        tx = cx - s * (xmin + xmax) / 2.0
        ty = y1 + s * ymin
        out.append((d, f"translate({tx:.2f} {ty:.2f}) scale({s:.5f} -{s:.5f})"))
    return out

texto = []
for r in regions:
    ttf, chars = FONTS[r["text"]]
    boxes = r["glyph_boxes"]
    assert len(chars) == len(boxes), (r["text"], len(chars), len(boxes))
    texto.extend(region_glyph_paths(ttf, chars, boxes))

# ── 3. componer SVG ──
svg = ET.Element("svg", {
    "xmlns": "http://www.w3.org/2000/svg", "version": "1.1",
    "width": str(w), "height": str(h), "viewBox": f"0 0 {w} {h}",
})
defs = ET.SubElement(svg, "defs")
style = ET.SubElement(defs, "style")
style.text = (f".ink {{ fill: {ink}; fill-rule: evenodd; stroke: none; }} "
              f".type {{ fill: {ink}; stroke: none; }}")

g_ink = ET.SubElement(svg, "g", {"class": "ink"})
for d in caligrafia:
    ET.SubElement(g_ink, "path", {"d": d})

g_type = ET.SubElement(svg, "g", {"class": "type"})
for d, tr in texto:
    ET.SubElement(g_type, "path", {"d": d, "transform": tr})

tree = ET.ElementTree(svg)
tree.write(OUT_SVG, encoding="utf-8", xml_declaration=True)
kb = Path(OUT_SVG).stat().st_size / 1024
print(f"OK -> {OUT_SVG} ({kb:.0f} KB)")
