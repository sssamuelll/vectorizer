"""Preview final: original | hibrido, completo y zooms apilados."""
import sys

sys.stdout.reconfigure(encoding="utf-8")

import cv2
import numpy as np

ORIG = r"C:\Users\simon\Desktop\Ale\logo_ale.jpeg"
RENDER = r"C:\Users\simon\Desktop\Ale\_render_perfecto.png"
OUT = r"C:\Users\simon\Desktop\Ale\logo_ale_perfecto_preview.png"

orig = cv2.imread(ORIG)
ren = cv2.imread(RENDER)

sep_v = np.zeros((orig.shape[0], 4, 3), np.uint8)
full = np.hstack([orig, sep_v, ren])
full = cv2.resize(full, None, fx=0.55, fy=0.55, interpolation=cv2.INTER_AREA)

rows = [full]
for y0, y1, x0, x1 in [(620, 730, 470, 1020), (775, 835, 290, 1215)]:
    a = orig[y0:y1, x0:x1]
    b = ren[y0:y1, x0:x1]
    sep = np.zeros((a.shape[0], 4, 3), np.uint8)
    row = np.hstack([a, sep, b])
    scale = full.shape[1] / row.shape[1]
    row = cv2.resize(row, (full.shape[1], int(row.shape[0] * scale)),
                     interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
    rows.append(np.zeros((8, full.shape[1], 3), np.uint8))
    rows.append(row)

cv2.imwrite(OUT, np.vstack(rows))
print("OK ->", OUT)
