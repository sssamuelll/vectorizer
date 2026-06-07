"""Reconstruye el grupo de texto del entregable: mente -> Nanum Myeongjo 400
(decision visual de Samuel, bake-off de la 'e'), INTEGRATIVE -> STIX Two Text 600.
La caligrafia (ya suavizada con filtro sigma=2) no se toca.
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

import json
from pathlib import Path

import numpy as np
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

BOXES = r"C:\Users\simon\Desktop\Ale\_boxes.json"
SVG = r"C:\Users\simon\Desktop\Ale\logo_ale_perfecto.svg"
CACHE = Path.home() / ".cache" / "vectorizer-fonts"

FONTS = {
    "mente": (CACHE / "Nanum_Myeongjo_400.ttf", "mente"),
    "INTEGRATIVE PSYCHOLOGY": (CACHE / "STIX_Two_Text_600.ttf",
                               "INTEGRATIVEPSYCHOLOGY"),
}

regions = json.load(open(BOXES, encoding="utf-8"))


def region_glyph_paths(ttf_path, chars, glyph_boxes):
    font = TTFont(str(ttf_path))
    glyph_set = font.getGlyphSet()
    cmap = font.getBestCmap()
    info = []
    for ch in chars:
        gname = cmap[ord(ch)]
        bp = BoundsPen(glyph_set)
        glyph_set[gname].draw(bp)
        info.append((ch, gname, bp.bounds))
    ratios = [(y1 - y0) / (fb[3] - fb[1])
              for (ch, gn, fb), (x0, y0, x1, y1) in zip(info, glyph_boxes)
              if fb[3] - fb[1] > 0]
    s = float(np.median(ratios))
    print(f"  {ttf_path.name}: escala comun {s:.5f}")
    out = []
    for (ch, gname, fb), (x0, y0, x1, y1) in zip(info, glyph_boxes):
        pen = SVGPathPen(glyph_set)
        glyph_set[gname].draw(pen)
        d = pen.getCommands()
        xmin, ymin, xmax, ymax = fb
        cx = (x0 + x1) / 2.0
        tx = cx - s * (xmin + xmax) / 2.0
        ty = y1 + s * ymin
        out.append(f'<path d="{d}" transform="translate({tx:.2f} {ty:.2f}) scale({s:.5f} -{s:.5f})" />')
    return out

paths = []
for r in regions:
    ttf, chars = FONTS[r["text"]]
    assert len(chars) == len(r["glyph_boxes"])
    paths.extend(region_glyph_paths(ttf, chars, r["glyph_boxes"]))

svg = open(SVG, encoding="utf-8").read()
i0 = svg.index('<g class="type">')
i1 = svg.index("</g>", i0) + 4
nuevo = '<g class="type">' + "".join(paths) + "</g>"
svg = svg[:i0] + nuevo + svg[i1:]
with open(SVG, "w", encoding="utf-8") as f:
    f.write(svg)
print(f"OK -> {SVG} ({Path(SVG).stat().st_size // 1024} KB)")
