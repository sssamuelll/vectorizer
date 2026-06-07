"""Crops ampliados original vs render para las zonas criticas."""
import sys

sys.stdout.reconfigure(encoding="utf-8")

import cv2
import numpy as np

ORIG = r"C:\Users\simon\Desktop\Ale\logo_ale.jpeg"
RENDER = r"C:\Users\simon\Desktop\Ale\_render_fullres.png"

orig = cv2.imread(ORIG)
ren = cv2.imread(RENDER)

# zonas: (nombre, y0, y1, x0, x1, zoom)
ZONAS = [
    ("mente", 600, 780, 430, 1080, 2),
    ("integrative", 790, 880, 270, 1240, 2),
    ("caligrafia", 280, 560, 300, 720, 2),
    ("pajaros", 30, 240, 1050, 1350, 2),
]

for name, y0, y1, x0, x1, z in ZONAS:
    a = orig[y0:y1, x0:x1]
    b = ren[y0:y1, x0:x1]
    a = cv2.resize(a, None, fx=z, fy=z, interpolation=cv2.INTER_NEAREST)
    b = cv2.resize(b, None, fx=z, fy=z, interpolation=cv2.INTER_NEAREST)
    sep = np.zeros((6, a.shape[1], 3), np.uint8)
    comp = np.vstack([a, sep, b])
    out = rf"C:\Users\simon\Desktop\Ale\_zoom_{name}.png"
    cv2.imwrite(out, comp)
    print("OK", out, comp.shape)
