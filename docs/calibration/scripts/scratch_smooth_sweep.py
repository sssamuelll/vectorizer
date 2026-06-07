"""Barrido de suavizado SOLO en la caligrafia del hibrido.

Genera variantes (blur, rdp, chaikin), renderiza, y produce:
- metrica de fidelidad (XOR binario vs original, fuera de regiones de texto)
- crops zoom apilados para juicio visual
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

import json
from pathlib import Path

import cv2
import numpy as np
import resvg_py

from vectorize import clean_binary_mask, trace_contours

ORIG = r"C:\Users\simon\Desktop\Ale\logo_ale.jpeg"
BOXES = r"C:\Users\simon\Desktop\Ale\_boxes.json"
BASE_SVG = r"C:\Users\simon\Desktop\Ale\logo_ale_perfecto.svg"
PAD = 6

# variantes: (nombre, blur_k, rdp_eps_trace, chaikin_trace)
# actual (winner B) = blur 3px kernel, rdp 0.5, chaikin 2
VARIANTES = [
    ("actual", 3, 0.5, 2),
    ("v1_rdp08", 3, 0.8, 2),
    ("v2_rdp12", 3, 1.2, 2),
    ("v3_rdp08_ch3", 3, 0.8, 3),
    ("v4_blur5_rdp08", 5, 0.8, 2),
]

orig = cv2.imread(ORIG)
h, w = orig.shape[:2]
regions = json.load(open(BOXES, encoding="utf-8"))

masked = orig.copy()
text_mask = np.zeros((h, w), np.uint8)
for r in regions:
    x0, y0, x1, y1 = r["bbox"]
    masked[max(0, y0 - PAD):min(h, y1 + PAD),
           max(0, x0 - PAD):min(w, x1 + PAD)] = 255
    text_mask[max(0, y0 - PAD):min(h, y1 + PAD),
              max(0, x0 - PAD):min(w, x1 + PAD)] = 255

# binario de referencia del original (sin blur, para medir fidelidad)
gray_ref = cv2.cvtColor(masked, cv2.COLOR_BGR2GRAY)
_, bin_ref = cv2.threshold(gray_ref, 0, 255,
                           cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)

# el SVG base ya tiene el grupo de texto perfecto: lo reutilizamos
base = open(BASE_SVG, encoding="utf-8").read()
i0 = base.index('<g class="ink">')
i1 = base.index("</g>", i0) + 4
prefix, suffix = base[:i0], base[i1:]

renders = {}
for name, blur_k, rdp, ch in VARIANTES:
    gray = cv2.cvtColor(masked, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (blur_k, blur_k), 0)
    _, binary = cv2.threshold(gray, 0, 255,
                              cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE,
                              np.ones((2, 2), np.uint8), iterations=1)
    binary = clean_binary_mask(binary)
    paths = trace_contours(binary, rdp_eps=rdp, chaikin_iter=ch, tension=0.5)

    g = '<g class="ink">' + "".join(f'<path d="{d}" />' for d in paths) + "</g>"
    svg = prefix + g + suffix

    png = bytes(resvg_py.svg_to_bytes(svg_string=svg))
    arr = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED)
    a = arr[:, :, 3:4].astype(np.float32) / 255.0
    arr = (arr[:, :, :3].astype(np.float32) * a + 255.0 * (1 - a)).astype(np.uint8)
    renders[name] = arr

    g2 = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    _, bin_r = cv2.threshold(g2, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    bin_r[text_mask > 0] = 0
    xor = cv2.bitwise_xor(bin_ref, bin_r)
    fid = int((xor > 0).sum())
    n_seg = sum(d.count("C") for d in paths)
    print(f"{name:18s} XOR={fid:6d}px  paths={len(paths)}  segC={n_seg:6d}  ({Path(BASE_SVG).name} len g={len(g)//1024}KB)")

    if name != "actual":
        out_svg = rf"C:\Users\simon\Desktop\Ale\_variant_{name}.svg"
        with open(out_svg, "w", encoding="utf-8") as f:
            f.write(svg)

# crops zoom: zonas de alta curvatura de la caligrafia
ZONAS = [("bowl_b", 380, 560, 540, 800), ("swash", 430, 580, 880, 1260)]
for zname, y0, y1, x0, x1 in ZONAS:
    tiles = [cv2.resize(orig[y0:y1, x0:x1], None, fx=2, fy=2,
                        interpolation=cv2.INTER_NEAREST)]
    for name, *_ in VARIANTES:
        t = cv2.resize(renders[name][y0:y1, x0:x1], None, fx=2, fy=2,
                       interpolation=cv2.INTER_NEAREST)
        tiles.append(t)
    sep = np.zeros((6, tiles[0].shape[1], 3), np.uint8)
    stacked = tiles[0]
    for t in tiles[1:]:
        stacked = np.vstack([stacked, sep, t])
    out = rf"C:\Users\simon\Desktop\Ale\_sweep_{zname}.png"
    cv2.imwrite(out, stacked)
    print("OK", out, "(orden: original, " + ", ".join(v[0] for v in VARIANTES) + ")")
