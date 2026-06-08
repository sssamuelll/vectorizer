#!/usr/bin/env python3
"""recompose_core.py — compose híbrido compartido (CLI y backend web).

Funciones puras que ambos orquestadores importan: resolución de TTF, glifos
desde TTF, caligrafía vectorizada, compositor SVG, y el cableado de compose
(compose_hybrid_svg) como dueño único de esa política.

Dependencia unidireccional: este módulo NO importa de recompose.py.
Superficie de import CERRADA (test AST la vigila):
  fontid:    download_family_weights
  vectorize: clean_binary_mask, extract_stroke_color, trace_contours
"""
import hashlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

from fontid import download_family_weights
from vectorize import clean_binary_mask, extract_stroke_color, trace_contours

# precondición una tinta (spec §7)
COLOR_WARN_THRESHOLD = 12

# caligrafía: ganadores del barrido de calibración
CALLIG_RDP = 0.8
CALLIG_CHAIKIN = 2
CALLIG_TENSION = 0.5
MASK_PAD = 6

# ── (a continuación, las definiciones movidas verbatim, en el orden de arriba) ──


class FontKeyError(Exception):
    """--font no matchea ninguna región (error duro, spec §5)."""


@dataclass
class SeamDecision:
    recompose: bool
    reason: str


def seam_decision(region, has_font=False):
    """La costura (spec §3): classify_region es EL árbitro. El corte 0.65
    vive DENTRO de fontid (label 'type' ya lo implica). Política
    provisional con evidencia N=1 — declarada, no escondida.

    has_font=True: --font explícito para esta región → recompone aunque
    el ranking esté vacío (offline sovereignty, HF2)."""
    if region.classification != "type":
        return SeamDecision(False, f"clasificada {region.classification} "
                                   f"(score {region.class_score:.2f})")
    if has_font or region.ranking:
        return SeamDecision(True, f"type (score {region.class_score:.2f})")
    return SeamDecision(False, "type pero sin fuente: ni --font ni ranking "
                               "(¿red caída?)")


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


def region_glyph_paths(ttf_path, chars, glyph_boxes, family):
    """[(path_d, transform)] por glifo. chars SIN espacios, len == len(boxes)
    (la costura ya lo garantizó). FontKeyError si TTF corrupto, sin cmap,
    char ausente o glifo sin bounds."""
    try:
        font = TTFont(str(ttf_path))
    except Exception as e:
        raise FontKeyError(
            f"no se pudo cargar la fuente {family!r} ({ttf_path.name}): {e}")
    glyph_set = font.getGlyphSet()
    cmap = font.getBestCmap()
    if cmap is None:
        raise FontKeyError(
            f"la fuente {family!r} no tiene tabla cmap Unicode")
    info = []
    for ch in chars:
        if ord(ch) not in cmap:
            raise FontKeyError(
                f"la fuente {family!r} no tiene glifo para {ch!r}")
        gname = cmap[ord(ch)]
        bp = BoundsPen(glyph_set)
        glyph_set[gname].draw(bp)
        if bp.bounds is None:
            raise FontKeyError(
                f"la fuente {family!r} no dibuja glifo para {ch!r}")
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
    # Sanitizar la clave de caché: rechazar ruta traversal (spec HF5)
    if any(sep in family for sep in ("/", "\\", "..")) or family != family.strip():
        raise FontKeyError(f"nombre de familia inválido: {family!r}")

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


def compose_svg(w, h, ink, callig_paths, glyph_pairs, provenance=None):
    """SVG híbrido: grupo .ink (caligrafía) + grupo .type (texto TTF).

    provenance: lista de strings «familia:peso sha256:<hex>» que se emiten
    como comentario XML antes del primer grupo (spec §8 — trazabilidad barata
    de la deriva upstream).
    """
    svg = ET.Element("svg", {
        "xmlns": "http://www.w3.org/2000/svg", "version": "1.1",
        "width": str(w), "height": str(h), "viewBox": f"0 0 {w} {h}",
    })
    defs = ET.SubElement(svg, "defs")
    style = ET.SubElement(defs, "style")
    style.text = (f".ink {{ fill: {ink}; fill-rule: evenodd; stroke: none; }} "
                  f".type {{ fill: {ink}; stroke: none; }}")
    if provenance:
        svg.append(ET.Comment(" TTF provenance: " + "; ".join(provenance) + " "))
    g_ink = ET.SubElement(svg, "g", {"class": "ink"})
    for d in callig_paths:
        ET.SubElement(g_ink, "path", {"d": d})
    g_type = ET.SubElement(svg, "g", {"class": "type"})
    for d, tr in glyph_pairs:
        ET.SubElement(g_type, "path", {"d": d, "transform": tr})
    return ET.tostring(svg, encoding="unicode")


@dataclass
class ComposeResult:
    """Salida del compose híbrido — interfaz para CLI (imprime stats) y backend
    (devuelve svg + provenance)."""
    svg_text: str
    ink: str
    callig_count: int
    glyph_count: int
    provenance: list      # [str] «familia:peso sha256:<hex>»
    mask_boxes: list      # [bbox] de las regiones recompuestas


@dataclass
class ChoiceResolution:
    """Salida de resolve_choices — la política empate>líder>error con un solo dueño."""
    effective: dict      # {idx: (family, wght)} USABLES (explícitas∩recomp + relleno de líder; sin ignoradas)
    recomp_idx: list     # [idx] a recomponer
    decisions: list      # [SeamDecision] por región — payload de reporte del CLI, NO del contrato de resolución
    pendientes: list     # [(idx, region)] empate sin elección
    ignoradas: list      # [idx] choices apuntando a región NO recompuesta


def resolve_choices(regions, choices):
    """Política empate>líder>error, extraída verbatim de main() (recompose.py).
    choices: {idx: (family, wght)} EXPLÍCITAS. has_font se evalúa contra las
    explícitas (orden canónico de main), no contra el relleno. Función PURA: no
    imprime — el orquestador presenta (CLI: stderr/exit; backend: HTTP)."""
    decisions = [seam_decision(r, has_font=(i in choices))
                 for i, r in enumerate(regions)]
    recomp_idx = [i for i, d in enumerate(decisions) if d.recompose]
    ignoradas = [i for i in choices if i not in recomp_idx]
    effective = {i: v for i, v in choices.items() if i not in ignoradas}
    pendientes = []
    for i in recomp_idx:
        if i in effective:
            continue
        r = regions[i]
        lider = r.ranking[0]
        empate = len(r.ranking) > 1 and r.ranking[1].tie
        if empate:
            pendientes.append((i, r))
        else:
            effective[i] = (lider.family, lider.wght)
    return ChoiceResolution(effective, recomp_idx, decisions, pendientes, ignoradas)


def region_overlay_paths(region, family, wght, cache_dir):
    """[(path_d, transform)] de UNA región con una candidata, en coords de imagen
    completa — la unidad por región que compose_hybrid_svg usa, extraída para que
    el overlay del backend (Spec C0) la reuse: el ojo juzga exactamente lo que
    /compose va a producir. Devuelve (pairs, ttf_path); compose necesita el
    ttf_path para el sha de procedencia. FontKeyError si la fuente falla."""
    ttf = resolve_ttf(family, wght, cache_dir)
    chars = [c for c in region.text if not c.isspace()]
    return region_glyph_paths(ttf, chars, region.glyph_boxes, family), ttf


def compose_hybrid_svg(img_bgr, regions, choices, recomp_idx, sigma, cache_dir):
    """Cableado de compose compartido (CLI y backend). Dado choices YA resueltos
    {idx: (family, wght)} y los índices a recomponer, compone el SVG híbrido.
    Dueño único de la política de compose. Lanza FontKeyError si el TTF falla —
    el orquestador decide cómo presentarlo (CLI: exit 4; backend: HTTP).

    Levantado verbatim del bloque inline de main() en recompose.py."""
    cache_dir = Path(cache_dir)
    glyph_pairs = []
    mask_boxes = []
    provenance = []
    for i in recomp_idx:
        r = regions[i]
        family, wght = choices[i]
        pairs, ttf = region_overlay_paths(r, family, wght, cache_dir)
        sha = hashlib.sha256(ttf.read_bytes()).hexdigest()[:16]
        provenance.append(f"{family}:{wght} sha256:{sha}")
        glyph_pairs.extend(pairs)
        mask_boxes.append(r.bbox)
    h, w = img_bgr.shape[:2]
    callig = calligraphy_paths(img_bgr, mask_boxes, sigma=sigma)
    ink = extract_stroke_color(img_bgr, binary_ink_mask(img_bgr))
    svg_text = compose_svg(w, h, ink, callig, glyph_pairs, provenance=provenance)
    return ComposeResult(svg_text, ink, len(callig), len(glyph_pairs),
                         provenance, mask_boxes)
