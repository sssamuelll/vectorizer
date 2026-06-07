"""Render SVG -> PNG con resvg_py y arma comparacion lado a lado con el original."""
import sys

sys.stdout.reconfigure(encoding="utf-8")

import resvg_py
import cv2
import numpy as np

SVG = r"C:\Users\simon\Desktop\Ale\logo_ale_fullres.svg"
ORIG = r"C:\Users\simon\Desktop\Ale\logo_ale.jpeg"
OUT_RENDER = r"C:\Users\simon\Desktop\Ale\_render_fullres.png"
OUT_COMPARE = r"C:\Users\simon\Desktop\Ale\_compare.png"

svg_str = open(SVG, encoding="utf-8").read()
png_bytes = bytes(resvg_py.svg_to_bytes(svg_string=svg_str))
arr = cv2.imdecode(np.frombuffer(png_bytes, np.uint8), cv2.IMREAD_UNCHANGED)
print("render shape:", arr.shape)

# componer sobre blanco si hay alpha
if arr.shape[2] == 4:
    alpha = arr[:, :, 3:4].astype(np.float32) / 255.0
    rgb = arr[:, :, :3].astype(np.float32)
    arr = (rgb * alpha + 255.0 * (1.0 - alpha)).astype(np.uint8)

cv2.imwrite(OUT_RENDER, arr)

orig = cv2.imread(ORIG)
print("original shape:", orig.shape)

# escalar render al tamaño del original si difiere
if arr.shape[:2] != orig.shape[:2]:
    arr = cv2.resize(arr, (orig.shape[1], orig.shape[0]), interpolation=cv2.INTER_AREA)

sep = np.full((orig.shape[0], 4, 3), 0, np.uint8)
comp = np.hstack([orig, sep, arr])
cv2.imwrite(OUT_COMPARE, comp)
print("OK ->", OUT_COMPARE)
