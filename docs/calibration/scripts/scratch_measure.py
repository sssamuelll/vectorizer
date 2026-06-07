"""Mide escala/posicion del texto en el render vs el original."""
import sys

sys.stdout.reconfigure(encoding="utf-8")

import json

import cv2
import numpy as np

from fontid import segment_glyphs_with_boxes

ORIG = r"C:\Users\simon\Desktop\Ale\logo_ale.jpeg"
RENDER = r"C:\Users\simon\Desktop\Ale\_render_perfecto.png"
BOXES = r"C:\Users\simon\Desktop\Ale\_boxes.json"

orig = cv2.imread(ORIG)
ren = cv2.imread(RENDER)
regions = json.load(open(BOXES, encoding="utf-8"))

PAD = 12
for r in regions:
    x0, y0, x1, y1 = r["bbox"]
    co = orig[y0 - PAD:y1 + PAD, x0 - PAD:x1 + PAD]
    cr = ren[y0 - PAD:y1 + PAD, x0 - PAD:x1 + PAD]
    _, bo = segment_glyphs_with_boxes(co)
    _, br = segment_glyphs_with_boxes(cr)
    print(f"\n[{r['text']}] glifos orig={len(bo)} render={len(br)}")
    if len(bo) != len(br):
        print("  (conteo distinto, comparando por orden los primeros comunes)")
    n = min(len(bo), len(br))
    dh, dcx, dbot = [], [], []
    for i in range(n):
        ox0, oy0, ox1, oy1 = bo[i]
        rx0, ry0, rx1, ry1 = br[i]
        h_o, h_r = oy1 - oy0, ry1 - ry0
        dh.append(h_r / h_o if h_o else 0)
        dcx.append(((rx0 + rx1) - (ox0 + ox1)) / 2.0)
        dbot.append(ry1 - oy1)
    print(f"  altura render/orig: mediana {np.median(dh):.3f}  (min {min(dh):.3f} max {max(dh):.3f})")
    print(f"  delta centro-x px:  mediana {np.median(dcx):+.1f}  (min {min(dcx):+.1f} max {max(dcx):+.1f})")
    print(f"  delta fondo px:     mediana {np.median(dbot):+.1f}  (min {min(dbot):+.1f} max {max(dbot):+.1f})")
