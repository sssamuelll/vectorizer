"""Zoom 4x: trazo largo diagonal, pajaro chico, lazo del 'e'."""
import sys

sys.stdout.reconfigure(encoding="utf-8")

import cv2
import numpy as np
import resvg_py

ORIG = r"C:\Users\simon\Desktop\Ale\logo_ale.jpeg"
SVGS = [
    ("actual", r"C:\Users\simon\Desktop\Ale\logo_ale_perfecto.svg"),
    ("v1_rdp08", r"C:\Users\simon\Desktop\Ale\_variant_v1_rdp08.svg"),
    ("v2_rdp12", r"C:\Users\simon\Desktop\Ale\_variant_v2_rdp12.svg"),
    ("v4_blur5_rdp08", r"C:\Users\simon\Desktop\Ale\_variant_v4_blur5_rdp08.svg"),
]

imgs = {"original": cv2.imread(ORIG)}
for name, p in SVGS:
    png = bytes(resvg_py.svg_to_bytes(svg_string=open(p, encoding="utf-8").read()))
    arr = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED)
    a = arr[:, :, 3:4].astype(np.float32) / 255.0
    imgs[name] = (arr[:, :, :3].astype(np.float32) * a + 255.0 * (1 - a)).astype(np.uint8)

ZONAS = [
    ("diagonal", 250, 400, 580, 720),   # ascender del 'b'
    ("pajarito", 410, 470, 1090, 1180), # pajaro mas chico
    ("lazo_e", 430, 530, 830, 950),     # lazo del 'e' final de libre
]
for zname, y0, y1, x0, x1 in ZONAS:
    tiles = []
    for name in imgs:
        t = cv2.resize(imgs[name][y0:y1, x0:x1], None, fx=4, fy=4,
                       interpolation=cv2.INTER_NEAREST)
        tiles.append(t)
    sep = np.zeros((tiles[0].shape[0], 8, 3), np.uint8)
    row = tiles[0]
    for t in tiles[1:]:
        row = np.hstack([row, sep, t])
    out = rf"C:\Users\simon\Desktop\Ale\_z4_{zname}.png"
    cv2.imwrite(out, row)
    print("OK", out, "(orden: " + ", ".join(imgs) + ")")
