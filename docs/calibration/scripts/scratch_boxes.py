"""Extrae boxes absolutos de regiones de texto + glifos del logo de Ale."""
import sys

sys.stdout.reconfigure(encoding="utf-8")

import json

import cv2

from fontid import detect_regions, segment_glyphs_with_boxes
from vectorize import load_image_bgr

ORIG = r"C:\Users\simon\Desktop\Ale\logo_ale.jpeg"
OUT = r"C:\Users\simon\Desktop\Ale\_boxes.json"

img = load_image_bgr(ORIG)
regions = detect_regions(img)

data = []
for r in regions:
    x0, y0, x1, y1 = r["bbox"]
    crop = img[y0:y1, x0:x1]
    masks, boxes = segment_glyphs_with_boxes(crop)
    abs_boxes = [(int(bx0 + x0), int(by0 + y0), int(bx1 + x0), int(by1 + y0))
                 for bx0, by0, bx1, by1 in boxes]
    data.append({
        "text": r["text"],
        "bbox": [int(v) for v in (x0, y0, x1, y1)],
        "glyph_boxes": abs_boxes,
    })
    print(f"[{r['text']}] bbox={x0},{y0},{x1},{y1}  glifos={len(abs_boxes)}")
    for gb in abs_boxes:
        print("   ", gb)

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
print("OK ->", OUT)
