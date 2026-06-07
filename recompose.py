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
    ty = y1 - s * ymin
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


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # cp1252 crashea con Δ/→
    raise SystemExit("recompose.py: implementación en progreso (Task 11)")


if __name__ == "__main__":
    main()
