"""XOR binario global original vs render: caza trazos perdidos o sobrantes."""
import sys

sys.stdout.reconfigure(encoding="utf-8")

import cv2
import numpy as np

ORIG = r"C:\Users\simon\Desktop\Ale\logo_ale.jpeg"
RENDER = r"C:\Users\simon\Desktop\Ale\_render_perfecto.png"
OUT = r"C:\Users\simon\Desktop\Ale\_diff.png"


def binarize(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, b = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    return b


o = binarize(cv2.imread(ORIG))
r = binarize(cv2.imread(RENDER))

xor = cv2.bitwise_xor(o, r)
# tolerancia: erosionar 2px — solo quedan discrepancias gordas
tol = cv2.erode(xor, np.ones((5, 5), np.uint8))

n, labels, stats, _ = cv2.connectedComponentsWithStats((tol > 0).astype(np.uint8), 8)
big = [(stats[i][4], tuple(int(v) for v in stats[i][:4])) for i in range(1, n) if stats[i][4] >= 30]
big.sort(reverse=True)
print(f"pixeles en disputa (tras tolerancia 2px): {int((tol > 0).sum())}")
print(f"clusteres >=30px: {len(big)}")
for area, (x, y, w, h) in big[:15]:
    print(f"  area={area:5d}  x={x} y={y} w={w} h={h}")

# visual: original gris, faltante en rojo (en orig, no en render), sobrante en azul
vis = cv2.cvtColor(255 - o // 2, cv2.COLOR_GRAY2BGR)
falta = (o > 0) & (r == 0)
sobra = (r > 0) & (o == 0)
vis[falta] = (0, 0, 220)
vis[sobra] = (220, 80, 0)
cv2.imwrite(OUT, vis)
print("OK ->", OUT)
