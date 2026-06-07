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


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # cp1252 crashea con Δ/→
    raise SystemExit("recompose.py: implementación en progreso (Task 11)")


if __name__ == "__main__":
    main()
