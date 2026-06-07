#!/usr/bin/env python3
"""recompose.py — Fase B v0.1 (replay puro).

Logo de UNA tinta → SVG híbrido: caligrafía vectorizada desde la imagen
(filtro sigma) + texto recompuesto desde el TTF de la fuente aproximada,
colocado glifo a glifo en las posiciones del original.

El producto NO "recompone logos": propone una recomposición y da
superficies baratas para corregirla (preview + comandos --font).
Spec: docs/superpowers/specs/2026-06-07-fontid-fase-b-design.md

Superficie de import CERRADA (test AST la vigila):
  fontid:    analyze_regions, download_family_weights, CACHE_DIR_DEFAULT
  vectorize: load_image_bgr, trace_contours, extract_stroke_color,
             clean_binary_mask
"""
import argparse
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

from fontid import CACHE_DIR_DEFAULT, analyze_regions, download_family_weights
from vectorize import (clean_binary_mask, extract_stroke_color,
                       load_image_bgr, trace_contours)

# exit codes (spec §7)
EXIT_NADA_QUE_RECOMPONER = 2
EXIT_EMPATE_PENDIENTE = 3
EXIT_FONT_KEY = 4

# caligrafía: ganadores del barrido de calibración (sigma=2 + rdp 0.8 + chaikin 2)
CALLIG_RDP = 0.8
CALLIG_CHAIKIN = 2
CALLIG_TENSION = 0.5
MASK_PAD = 6


class FontKeyError(Exception):
    """--font no matchea ninguna región (error duro, spec §5)."""


def _norm_key(s):
    """Normalización de claves --font: casefold + colapso de espacios."""
    return " ".join(s.casefold().split())


def parse_font_arg(raw):
    """'clave=Familia:wght' → (clave, familia, wght). ValueError si malformado."""
    key, sep, value = raw.partition("=")
    if not sep or not key or ":" not in value:
        raise ValueError(
            f'--font malformado: {raw!r} (esperado "texto=Familia:wght" '
            f'o "#N=Familia:wght")')
    family, _, wght_s = value.rpartition(":")
    if not family or not wght_s.isdigit():
        raise ValueError(f"--font sin peso numérico: {raw!r}")
    return key, family.strip(), int(wght_s)


def resolve_font_choices(font_args, regions):
    """[--font strings] + [RegionAnalysis] → {índice_región: (familia, wght)}.

    Clave por texto: match EXACTO post-normalización. Clave '#N': región
    N (1-based). No-match → FontKeyError con las claves disponibles
    (jamás degradación silenciosa — rompería el replay).
    """
    norm_texts = [_norm_key(r.text) for r in regions]
    out = {}
    for raw in font_args:
        key, family, wght = parse_font_arg(raw)
        if key.startswith("#"):
            idx_s = key[1:]
            if not idx_s.isdigit() or not (1 <= int(idx_s) <= len(regions)):
                raise FontKeyError(
                    f"índice {key!r} fuera de rango (hay {len(regions)} regiones)")
            out[int(idx_s) - 1] = (family, wght)
            continue
        nk = _norm_key(key)
        matches = [i for i, t in enumerate(norm_texts) if t == nk]
        if not matches:
            raise FontKeyError(
                f"--font {key!r} no matchea ninguna región. Disponibles: "
                + ", ".join(repr(r.text) for r in regions))
        if len(matches) > 1:
            raise FontKeyError(
                f"--font {key!r} matchea {len(matches)} regiones — usa #N")
        out[matches[0]] = (family, wght)
    return out


@dataclass
class SeamDecision:
    recompose: bool
    reason: str


def seam_decision(region):
    """La costura (spec §3): classify_region es EL árbitro. El corte 0.65
    vive DENTRO de fontid (label 'type' ya lo implica). Política
    provisional con evidencia N=1 — declarada, no escondida."""
    if region.classification != "type":
        return SeamDecision(False, f"clasificada {region.classification} "
                                   f"(score {region.class_score:.2f})")
    if not region.ranking:
        return SeamDecision(False, "type sin ranking (conteo glifos≠chars "
                                   "o pool vacío) — se vectoriza")
    return SeamDecision(True, f"type (score {region.class_score:.2f})")


def print_seam_report(regions, decisions):
    """La costura SIEMPRE se reporta (junta: 'la frontera más peligrosa
    era la única sin ceremonia')."""
    print("Costura (qué se recompone vs qué se vectoriza):")
    for i, (r, d) in enumerate(zip(regions, decisions), 1):
        verbo = "recompone" if d.recompose else "vectoriza"
        print(f"  [{i}] \"{r.text}\" → se {verbo} — {d.reason}")


def common_scale(font_bboxes, glyph_boxes):
    """Escala COMÚN por región: mediana de (altura box original / altura
    glifo en font units). Misma filosofía que la métrica de matching —
    las proporciones relativas entre glifos sobreviven."""
    ratios = [(y1 - y0) / (fb[3] - fb[1])
              for fb, (x0, y0, x1, y1) in zip(font_bboxes, glyph_boxes)
              if fb is not None and fb[3] - fb[1] > 0]
    if not ratios:
        raise ValueError("ningún glifo con bbox válido para la escala")
    return float(np.median(ratios))


def glyph_transform(font_bbox, glyph_box, s):
    """Transform SVG: centro-x alineado, fondo del bbox alineado (el
    overshoot de las redondas viene gratis). Font units son y-up → scale -s."""
    xmin, ymin, xmax, ymax = font_bbox
    x0, y0, x1, y1 = glyph_box
    cx = (x0 + x1) / 2.0
    tx = cx - s * (xmin + xmax) / 2.0
    ty = y1 + s * ymin
    return f"translate({tx:.2f} {ty:.2f}) scale({s:.5f} -{s:.5f})"


def region_glyph_paths(ttf_path, chars, glyph_boxes):
    """[(path_d, transform)] por glifo. chars SIN espacios, len == len(boxes)
    (la costura ya lo garantizó). KeyError si un char no está en el cmap."""
    font = TTFont(str(ttf_path))
    glyph_set = font.getGlyphSet()
    cmap = font.getBestCmap()
    info = []
    for ch in chars:
        gname = cmap[ord(ch)]
        bp = BoundsPen(glyph_set)
        glyph_set[gname].draw(bp)
        info.append((gname, bp.bounds))
    s = common_scale([fb for _, fb in info], glyph_boxes)
    out = []
    for (gname, fb), box in zip(info, glyph_boxes):
        pen = SVGPathPen(glyph_set)
        glyph_set[gname].draw(pen)
        out.append((pen.getCommands(), glyph_transform(fb, box, s)))
    return out


def resolve_ttf(family, wght, cache_dir):
    """TTF de familia:peso — caché primero, descarga on-demand después.
    La familia puede NO estar en el ranking (regla de soberanía: el ojo
    elige fuera del menú — caso Nanum Myeongjo). Peso inexistente →
    FontKeyError con los disponibles."""
    cache_dir = Path(cache_dir)
    cached = cache_dir / f"{family.replace(' ', '_')}_{wght}.ttf"
    if cached.exists():
        return cached
    weights = download_family_weights(family, cache_dir)
    for w, path in weights:
        if w == wght:
            return path
    disponibles = sorted(w for w, _ in weights) or "ninguno (¿red caída o familia inexistente en GF?)"
    raise FontKeyError(
        f"peso {wght} no disponible para {family!r}; disponibles: {disponibles}")


def calligraphy_paths(img_bgr, mask_boxes, sigma, pad=MASK_PAD):
    """Vectoriza la tinta FUERA de las regiones a recomponer.

    mask_boxes: bboxes absolutas de las regiones recompuestas (se pintan
    de blanco con pad). clean_binary_mask es legítima AQUÍ (caligrafía) —
    y JAMÁS sobre crops de glifos (contradicción cross-spec resuelta,
    spec §4)."""
    h, w = img_bgr.shape[:2]
    masked = img_bgr.copy()
    for x0, y0, x1, y1 in mask_boxes:
        masked[max(0, y0 - pad):min(h, y1 + pad),
               max(0, x0 - pad):min(w, x1 + pad)] = 255
    gray = cv2.cvtColor(masked, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    _, binary = cv2.threshold(gray, 0, 255,
                              cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE,
                              np.ones((2, 2), np.uint8), iterations=1)
    binary = clean_binary_mask(binary)
    return trace_contours(binary, rdp_eps=CALLIG_RDP,
                          chaikin_iter=CALLIG_CHAIKIN,
                          tension=CALLIG_TENSION, sigma=sigma)


def binary_ink_mask(img_bgr):
    """Máscara binaria de la tinta completa (para extract_stroke_color)."""
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255,
                              cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    return binary


def compose_svg(w, h, ink, callig_paths, glyph_pairs):
    """SVG híbrido: grupo .ink (caligrafía) + grupo .type (texto TTF)."""
    svg = ET.Element("svg", {
        "xmlns": "http://www.w3.org/2000/svg", "version": "1.1",
        "width": str(w), "height": str(h), "viewBox": f"0 0 {w} {h}",
    })
    defs = ET.SubElement(svg, "defs")
    style = ET.SubElement(defs, "style")
    style.text = (f".ink {{ fill: {ink}; fill-rule: evenodd; stroke: none; }} "
                  f".type {{ fill: {ink}; stroke: none; }}")
    g_ink = ET.SubElement(svg, "g", {"class": "ink"})
    for d in callig_paths:
        ET.SubElement(g_ink, "path", {"d": d})
    g_type = ET.SubElement(svg, "g", {"class": "type"})
    for d, tr in glyph_pairs:
        ET.SubElement(g_type, "path", {"d": d, "transform": tr})
    return ET.tostring(svg, encoding="unicode")


def _render_svg(svg_text):
    """Render BGR del SVG vía resvg_py, o None si no está instalado.
    resvg_py es dependencia OPCIONAL (solo preview)."""
    try:
        import resvg_py
    except ImportError:
        return None
    png = bytes(resvg_py.svg_to_bytes(svg_string=svg_text))
    arr = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED)
    if arr is None:
        return None
    if arr.shape[2] == 4:
        a = arr[:, :, 3:4].astype(np.float32) / 255.0
        arr = (arr[:, :, :3].astype(np.float32) * a
               + 255.0 * (1 - a)).astype(np.uint8)
    return arr


def write_preview(orig_bgr, svg_text, region_boxes, out_path):
    """Preview = original | render (el original SIEMPRE presente como
    ancla — Iris: sin él es '¿cuál te gusta?' en vez de '¿cuál calza?'),
    más una banda de zoom por región recompuesta. None sin resvg."""
    render = _render_svg(svg_text)
    if render is None:
        print("  [WARN] resvg_py no disponible — preview omitido "
              "(pip install resvg_py)", file=sys.stderr)
        return None
    if render.shape[:2] != orig_bgr.shape[:2]:
        render = cv2.resize(render, (orig_bgr.shape[1], orig_bgr.shape[0]),
                            interpolation=cv2.INTER_AREA)
    sep_v = np.zeros((orig_bgr.shape[0], 4, 3), np.uint8)
    rows = [np.hstack([orig_bgr, sep_v, render])]
    for x0, y0, x1, y1 in region_boxes:
        a, b = orig_bgr[y0:y1, x0:x1], render[y0:y1, x0:x1]
        sep = np.zeros((a.shape[0], 4, 3), np.uint8)
        band = np.hstack([a, sep, b])
        scale = rows[0].shape[1] / band.shape[1]
        band = cv2.resize(band, (rows[0].shape[1],
                                 max(1, int(band.shape[0] * scale))),
                          interpolation=cv2.INTER_AREA if scale < 1
                          else cv2.INTER_CUBIC)
        rows.append(np.zeros((6, rows[0].shape[1], 3), np.uint8))
        rows.append(band)
    out_path = Path(out_path)
    cv2.imwrite(str(out_path), np.vstack(rows))
    return out_path


def print_correction_commands(input_path, regions, choices):
    """Eco sintáctico de una decisión visual (Iris: la superficie es el
    PNG; el comando es la sintaxis). Por región recompuesta: la usada +
    las 3 siguientes del ranking como re-corridas armadas."""
    print("\nCorrección (mira el preview; estas son las re-corridas):")
    for idx, (family, wght) in sorted(choices.items()):
        r = regions[idx]
        print(f"  [{idx + 1}] \"{r.text}\" — usada: {family} {wght}")
        alternativas = [e for e in r.ranking
                        if (e.family, e.wght) != (family, wght)][:3]
        for e in alternativas:
            print(f'      python recompose.py "{input_path}" '
                  f'--font "{r.text}={e.family}:{e.wght}"')


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # cp1252 crashea con Δ/→
    raise SystemExit("recompose.py: implementación en progreso (Task 11)")


if __name__ == "__main__":
    main()
