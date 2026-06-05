#!/usr/bin/env python3
"""
Spike Fase A.0 — Aproximación de fuentes tipográficas (Google Fonts).

NO identifica fuentes: aproxima. Encuentra la alternativa más cercana
dentro de Google Fonts. Ver docs/superpowers/specs/2026-06-05-font-identification-design.md

Uso:
    python fontid.py logo.png --region x0,y0,x1,y1 --text "mente"
"""

import argparse
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from vectorize import load_image_bgr

# ═══════════════════════════════════════════════════════════════════
# 1. SEGMENTACIÓN (sin fusión vertical — límite declarado del spike:
#    parte minúsculas con punto i/j y acentos; las palabras del caso
#    motivador no los tienen. La fusión es requisito de Fase A.)
# ═══════════════════════════════════════════════════════════════════

def _tight(mask):
    """Recorta una máscara booleana a su contenido."""
    ys, xs = np.where(mask)
    return mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def segment_glyphs(crop_bgr, min_area=4):
    """Binariza (Otsu directo — SIN clean_binary_mask, que destruye
    serifas/puntos por diseño) y devuelve las máscaras de los glifos
    como componentes conexos ordenados por x."""
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    flag = cv2.THRESH_BINARY_INV if np.mean(gray) > 127 else cv2.THRESH_BINARY
    _, binary = cv2.threshold(gray, 0, 255, flag | cv2.THRESH_OTSU)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(
        (binary > 0).astype(np.uint8), connectivity=8)
    comps = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < min_area:
            continue
        comps.append((x, labels[y:y + h, x:x + w] == i))
    comps.sort(key=lambda t: t[0])
    return [m for _, m in comps]


# ═══════════════════════════════════════════════════════════════════
# 2. RENDER + MATCHING (métrica del spec: factor de escala COMÚN —
#    las proporciones relativas entre glifos sobreviven y los
#    desajustes de tamaño penalizan el IoU. Solo la posición se
#    normaliza (centroide): el tracking es decisión del logo, no
#    de la fuente.)
# ═══════════════════════════════════════════════════════════════════

def render_glyph(ch, font):
    """Renderiza un carácter como máscara booleana recortada, o None."""
    bbox = font.getbbox(ch)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    if w <= 0 or h <= 0:
        return None
    img = Image.new("L", (w + 8, h + 8), 0)
    ImageDraw.Draw(img).text((4 - bbox[0], 4 - bbox[1]), ch, fill=255, font=font)
    arr = np.array(img) > 127
    if not arr.any():
        return None
    return _tight(arr)


def _iou_centroid(a, b):
    """IoU de dos máscaras alineadas por centroide en un canvas común
    (tamaño 2*max para que el pegado nunca recorte)."""
    H = 2 * max(a.shape[0], b.shape[0]) + 4
    W = 2 * max(a.shape[1], b.shape[1]) + 4

    def centered(m):
        c = np.zeros((H, W), dtype=bool)
        ys, xs = np.where(m)
        oy = int(round(H / 2 - ys.mean()))
        ox = int(round(W / 2 - xs.mean()))
        c[oy:oy + m.shape[0], ox:ox + m.shape[1]] = m
        return c

    A, B = centered(a), centered(b)
    union = np.logical_or(A, B).sum()
    if union == 0:
        return 0.0
    return float(np.logical_and(A, B).sum() / union)


def match_candidate(crop_glyphs, chars, ttf_path, base_size=96):
    """Score de una candidata contra los glifos del crop.

    Devuelve overlap en [0,1] (media truncada de IoU por glifo) o None
    si la región es insuficiente (<2 glifos) o el render falla.
    - ≥4 glifos → se descarta el peor (robustez);
    - 2-3 glifos → media simple;
    - <2 glifos → None ("insuficiente para matching").
    """
    if len(crop_glyphs) < 2 or len(crop_glyphs) != len(chars):
        return None
    font = ImageFont.truetype(str(ttf_path), base_size)
    rendered = [render_glyph(c, font) for c in chars]
    if any(r is None for r in rendered):
        return None

    # UN factor común, anclado a la altura mediana (spec, métrica del spike)
    crop_med = float(np.median([g.shape[0] for g in crop_glyphs]))
    rend_med = float(np.median([r.shape[0] for r in rendered]))
    if rend_med <= 0 or crop_med <= 0:
        return None
    s = crop_med / rend_med

    ious = []
    for g, r in zip(crop_glyphs, rendered):
        rs = cv2.resize(
            r.astype(np.uint8),
            (max(1, int(round(r.shape[1] * s))), max(1, int(round(r.shape[0] * s)))),
            interpolation=cv2.INTER_AREA) > 0
        if not rs.any():
            return None
        ious.append(_iou_centroid(g, rs))

    ious.sort()
    if len(ious) >= 4:
        ious = ious[1:]  # descarta el peor glifo
    return float(np.mean(ious))


# ═══════════════════════════════════════════════════════════════════
# 3. DESCARGA DE TTF (hecho runtime 3 del spec: el UA por defecto de
#    urllib entrega TTF directo — el "truco UA legacy" del v1 estaba
#    invertido y NO se usa. Validación antes de cachear + escritura
#    atómica: nunca queda un TTF a medias o corrupto en caché.)
# ═══════════════════════════════════════════════════════════════════

GF_CSS2 = "https://fonts.googleapis.com/css2?family={}"
TTF_MAGICS = (b"\x00\x01\x00\x00", b"OTTO", b"true")


def validate_ttf(path):
    """Magic bytes + apertura efectiva con Pillow. True si es usable."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return False
    if not any(data.startswith(m) for m in TTF_MAGICS):
        return False
    try:
        ImageFont.truetype(str(path), 24)
    except Exception:
        return False
    return True


def download_ttf(family, cache_dir):
    """Descarga el TTF regular de una familia GF a la caché.

    Devuelve la ruta cacheada, o None si la red/validación falla
    (el caller cuenta las omitidas y sigue — spec, tabla de errores).
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = cache_dir / (family.replace(" ", "_") + ".ttf")
    if dest.exists():
        return dest
    try:
        url = GF_CSS2.format(urllib.parse.quote_plus(family))
        css = urllib.request.urlopen(url, timeout=20).read().decode("utf-8")
        m = re.search(r"url\((https://[^)]+\.ttf)\)", css)
        if not m:
            return None
        data = urllib.request.urlopen(m.group(1), timeout=30).read()
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    # .tmp por familia: seguro solo en single-process (hecho runtime 7 del
    # spec: OCR/spike secuencial). Si Fase A paraleliza, usar tempfile único.
    tmp = dest.with_suffix(".tmp")
    tmp.write_bytes(data)
    if not validate_ttf(tmp):
        tmp.unlink(missing_ok=True)
        return None
    os.replace(tmp, dest)  # escritura atómica (spec)
    return dest


# ═══════════════════════════════════════════════════════════════════
# 4. POOLS, RANKING Y REPORTE
# ═══════════════════════════════════════════════════════════════════

SPIKE_POOL = [
    "Cormorant Garamond", "EB Garamond", "Cormorant SC", "Crimson Pro",
    "Crimson Text", "Sorts Mill Goudy", "Gilda Display", "Playfair Display",
    "Lora", "PT Serif", "Libre Baskerville", "Source Serif 4",
    "Noto Serif Display", "Cardo", "Spectral", "Domine",
    "Frank Ruhl Libre", "Marcellus", "Cinzel", "Old Standard TT",
]
# Controles negativos (sans/display/script): sin ellos la separación del
# cluster serif sería inmedible — son la línea base del gate (spec A.0).
CONTROLES = ["Roboto", "Montserrat", "Oswald", "Pacifico"]

TIE_DELTA = 0.03  # hecho runtime 6 del spec: margen serif-vs-serif real 0.027

CORPUS_NOTE = (
    "Corpus: Google Fonts. Si la fuente original es comercial, esto es la\n"
    "alternativa libre más cercana — no una identificación."
)


def tie_flags(ranked):
    """[(familia, overlap)] ordenado desc → [bool] EMPATE-con-el-líder."""
    if not ranked:
        return []
    leader = ranked[0][1]
    return [i > 0 and (leader - s) < TIE_DELTA for i, (_, s) in enumerate(ranked)]


def rank_region(crop_bgr, text, cache_dir):
    """Devuelve (ranked, controls, skipped, mismatch) para una región.

    mismatch: None, o (n_glifos, n_chars) si la segmentación no cuadra
    con el texto — la región se reporta y no se rankea.
    """
    glyphs = segment_glyphs(crop_bgr)
    chars = [c for c in text if not c.isspace()]
    if len(glyphs) != len(chars):
        return None, None, 0, (len(glyphs), len(chars))
    ranked, controls, skipped = [], [], 0
    for fam in SPIKE_POOL + CONTROLES:
        ttf = download_ttf(fam, cache_dir)
        if ttf is None:
            skipped += 1
            continue
        score = match_candidate(glyphs, chars, ttf)
        if score is None:
            continue
        (controls if fam in CONTROLES else ranked).append((fam, score))
    ranked.sort(key=lambda t: -t[1])
    controls.sort(key=lambda t: -t[1])
    return ranked, controls, skipped, None


def print_region_report(idx, text, ranked, controls, skipped, mismatch):
    print(f"\n[REGIÓN {idx}] \"{text}\"")
    if mismatch:
        print(f"  segmentación≠texto ({mismatch[0]} glifos vs {mismatch[1]} chars)"
              f" — no se rankea. ¿Puntos/acentos? (límite del spike)")
        return
    if not ranked:
        print("  sin candidatas rankeables")
        return
    ties = tie_flags(ranked)
    best_control = controls[0][1] if controls else 0.0
    sep = ranked[0][1] - best_control
    print(f"  separación del cluster vs controles: {sep:.3f} "
          f"({'OK' if sep > 0.1 else 'DÉBIL'} — gate condición 1)")
    prev = None
    for i, ((fam, s), tie) in enumerate(zip(ranked[:5], ties[:5]), 1):
        delta = f"   Δ {prev - s:.3f}" if prev is not None else ""
        mark = "  → EMPATE con el líder" if tie else ""
        print(f"  {i}. {fam:<22s} overlap {s:.3f}{delta}{mark}")
        prev = s
    for fam, s in controls:
        print(f"  [control] {fam:<14s} overlap {s:.3f}")
    if skipped:
        print(f"  ({skipped} candidatas omitidas por red/validación)")


# ═══════════════════════════════════════════════════════════════════
# 5. CLI
# ═══════════════════════════════════════════════════════════════════

def build_parser():
    p = argparse.ArgumentParser(
        description="Spike A.0 — aproximación de fuentes (Google Fonts). "
                    "NO identifica: aproxima.")
    p.add_argument("input", help="Imagen del logo")
    p.add_argument("--region", action="append", required=True,
                   help="x0,y0,x1,y1 (repetible, pareado con --text)")
    p.add_argument("--text", action="append", required=True,
                   help="Texto de la región (repetible, pareado con --region)")
    p.add_argument("--cache-dir", default="ttf_cache",
                   help="Caché de TTFs (default: ./ttf_cache)")
    return p


def validate_args(args):
    if len(args.region) != len(args.text):
        sys.exit(f"error: --region ({len(args.region)}) y --text "
                 f"({len(args.text)}) deben ir pareados posicionalmente")


def main():
    args = build_parser().parse_args()
    validate_args(args)
    img = load_image_bgr(args.input)
    if img is None:
        raise ValueError(f"No se pudo cargar: {args.input}")
    print(CORPUS_NOTE)
    for i, (reg, text) in enumerate(zip(args.region, args.text), 1):
        try:
            x0, y0, x1, y1 = (int(v) for v in reg.split(","))
        except ValueError:
            sys.exit(f"error: región inválida {reg!r} (formato x0,y0,x1,y1)")
        ranked, controls, skipped, mismatch = rank_region(
            img[y0:y1, x0:x1], text, args.cache_dir)
        print_region_report(i, text, ranked, controls, skipped, mismatch)


if __name__ == "__main__":
    main()
