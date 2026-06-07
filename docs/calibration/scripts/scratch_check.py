"""Render del hibrido + comparaciones zoom contra el original."""
import sys

sys.stdout.reconfigure(encoding="utf-8")

import cv2
import numpy as np
import resvg_py

SVG = r"C:\Users\simon\Desktop\Ale\logo_ale_perfecto.svg"
ORIG = r"C:\Users\simon\Desktop\Ale\logo_ale.jpeg"
OUT_RENDER = r"C:\Users\simon\Desktop\Ale\_render_perfecto.png"

svg_str = open(SVG, encoding="utf-8").read()
png = bytes(resvg_py.svg_to_bytes(svg_string=svg_str))
arr = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED)
if arr.shape[2] == 4:
    a = arr[:, :, 3:4].astype(np.float32) / 255.0
    arr = (arr[:, :, :3].astype(np.float32) * a + 255.0 * (1 - a)).astype(np.uint8)
cv2.imwrite(OUT_RENDER, arr)

orig = cv2.imread(ORIG)

ZONAS = [
    ("full", 0, 1044, 0, 1507, 0.49),
    ("mente", 610, 740, 460, 1030, 2),
    ("integrative", 770, 840, 280, 1220, 2),
]
for name, y0, y1, x0, x1, z in ZONAS:
    a = orig[y0:y1, x0:x1]
    b = arr[y0:y1, x0:x1]
    interp = cv2.INTER_AREA if z < 1 else cv2.INTER_NEAREST
    a = cv2.resize(a, None, fx=z, fy=z, interpolation=interp)
    b = cv2.resize(b, None, fx=z, fy=z, interpolation=interp)
    sep = np.zeros((6, a.shape[1], 3), np.uint8)
    comp = np.vstack([a, sep, b])
    out = rf"C:\Users\simon\Desktop\Ale\_chk_{name}.png"
    cv2.imwrite(out, comp)
    print("OK", out, comp.shape)
