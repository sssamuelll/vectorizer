"""Suavizado avanzado: filtro gaussiano circular sobre los puntos del
contorno ANTES de RDP — mata ruido de pixel sin deformar la forma.
Compara v2 (rdp 1.2) vs v5 (filtro sigma 2 + rdp 0.8) vs v6 (filtro sigma 3).
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

import json

import cv2
import numpy as np
import resvg_py

from vectorize import (_smooth_closed_contour, clean_binary_mask)

ORIG = r"C:\Users\simon\Desktop\Ale\logo_ale.jpeg"
BOXES = r"C:\Users\simon\Desktop\Ale\_boxes.json"
BASE_SVG = r"C:\Users\simon\Desktop\Ale\logo_ale_perfecto.svg"
PAD = 6


def gauss_filter_closed(pts, sigma):
    """Filtro gaussiano circular sobre un contorno cerrado (N,2)."""
    n = len(pts)
    if n < 8 or sigma <= 0:
        return pts
    radius = max(1, int(3 * sigma))
    xs = np.arange(-radius, radius + 1)
    k = np.exp(-(xs ** 2) / (2 * sigma ** 2))
    k /= k.sum()
    out = np.empty_like(pts)
    for d in range(2):
        col = pts[:, d]
        ext = np.concatenate([col[-radius:], col, col[:radius]])
        out[:, d] = np.convolve(ext, k, mode="valid")
    return out


def trace_filtered(binary, sigma, rdp_eps, chaikin_iter, tension=0.5,
                   min_outer_area=8, min_hole_area=8):
    contours, hierarchy = cv2.findContours(binary, cv2.RETR_CCOMP,
                                           cv2.CHAIN_APPROX_NONE)
    if hierarchy is None:
        return []
    hierarchy = hierarchy[0]
    children, outers = {}, []
    for i, h in enumerate(hierarchy):
        if h[3] == -1:
            outers.append(i)
        else:
            children.setdefault(h[3], []).append(i)
    paths = []
    for oi in outers:
        if cv2.contourArea(contours[oi]) < min_outer_area:
            continue
        pts = gauss_filter_closed(
            contours[oi].reshape(-1, 2).astype(np.float64), sigma)
        d_outer = _smooth_closed_contour(pts, rdp_eps, chaikin_iter, tension)
        if not d_outer:
            continue
        d_parts = [d_outer + " Z"]
        for hi in children.get(oi, []):
            if cv2.contourArea(contours[hi]) < min_hole_area:
                continue
            hpts = gauss_filter_closed(
                contours[hi].reshape(-1, 2).astype(np.float64), sigma)
            d_hole = _smooth_closed_contour(hpts, rdp_eps, chaikin_iter, tension)
            if d_hole:
                d_parts.append(d_hole + " Z")
        paths.append(" ".join(d_parts))
    return paths


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

gray_ref = cv2.cvtColor(masked, cv2.COLOR_BGR2GRAY)
_, bin_ref = cv2.threshold(gray_ref, 0, 255,
                           cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)

gray = cv2.GaussianBlur(gray_ref, (3, 3), 0)
_, binary = cv2.threshold(gray, 0, 255,
                          cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE,
                          np.ones((2, 2), np.uint8), iterations=1)
binary = clean_binary_mask(binary)

base = open(BASE_SVG, encoding="utf-8").read()
i0 = base.index('<g class="ink">')
i1 = base.index("</g>", i0) + 4
prefix, suffix = base[:i0], base[i1:]

# (nombre, sigma, rdp, chaikin)
VARIANTES = [
    ("v5_sig2", 2.0, 0.8, 2),
    ("v6_sig3", 3.0, 0.8, 2),
]
imgs = {"original": orig}
for name, sigma, rdp, ch in VARIANTES:
    paths = trace_filtered(binary, sigma, rdp, ch)
    g = '<g class="ink">' + "".join(f'<path d="{d}" />' for d in paths) + "</g>"
    svg = prefix + g + suffix
    out_svg = rf"C:\Users\simon\Desktop\Ale\_variant_{name}.svg"
    with open(out_svg, "w", encoding="utf-8") as f:
        f.write(svg)
    png = bytes(resvg_py.svg_to_bytes(svg_string=svg))
    arr = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED)
    a = arr[:, :, 3:4].astype(np.float32) / 255.0
    arr = (arr[:, :, :3].astype(np.float32) * a + 255.0 * (1 - a)).astype(np.uint8)
    imgs[name] = arr
    g2 = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    _, bin_r = cv2.threshold(g2, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    bin_r[text_mask > 0] = 0
    xor = int((cv2.bitwise_xor(bin_ref, bin_r) > 0).sum())
    nseg = sum(d.count("C") for d in paths)
    print(f"{name:10s} XOR={xor:6d}px  segC={nseg}  grupo={len(g)//1024}KB")

# añadir v2 para comparar
v2 = open(r"C:\Users\simon\Desktop\Ale\_variant_v2_rdp12.svg", encoding="utf-8").read()
png = bytes(resvg_py.svg_to_bytes(svg_string=v2))
arr = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED)
a = arr[:, :, 3:4].astype(np.float32) / 255.0
imgs["v2_rdp12"] = (arr[:, :, :3].astype(np.float32) * a + 255.0 * (1 - a)).astype(np.uint8)

ZONAS = [
    ("diagonal", 250, 400, 580, 720),
    ("pajarito", 410, 470, 1090, 1180),
    ("lazo_e", 430, 530, 830, 950),
]
orden = ["original", "v2_rdp12", "v5_sig2", "v6_sig3"]
for zname, y0, y1, x0, x1 in ZONAS:
    tiles = [cv2.resize(imgs[n][y0:y1, x0:x1], None, fx=4, fy=4,
                        interpolation=cv2.INTER_NEAREST) for n in orden]
    sep = np.zeros((tiles[0].shape[0], 8, 3), np.uint8)
    row = tiles[0]
    for t in tiles[1:]:
        row = np.hstack([row, sep, t])
    out = rf"C:\Users\simon\Desktop\Ale\_z5_{zname}.png"
    cv2.imwrite(out, row)
    print("OK", out, "(orden: " + ", ".join(orden) + ")")
