"""Tests de recompose_core.py (compose compartido)."""
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import recompose_core
import fontid


def _region(text="mente", bbox=(10, 10, 100, 40), classification="type",
            score=0.9, n_glyphs=5, ranking=None):
    gw = (bbox[2] - bbox[0]) // max(n_glyphs, 1)
    boxes = [(bbox[0] + i * gw, bbox[1], bbox[0] + i * gw + gw - 2, bbox[3])
             for i in range(n_glyphs)]
    return fontid.RegionAnalysis(
        bbox=bbox, text=text, classification=classification,
        class_score=score, glyph_boxes=boxes, ranking=ranking or [])


def _logo_sintetico():
    img = np.full((120, 300, 3), 255, np.uint8)
    cv2.ellipse(img, (150, 30), (100, 15), 0, 0, 360, (60, 110, 90), 6)
    for x in (60, 130, 200):
        cv2.rectangle(img, (x, 70), (x + 40, 110), (60, 110, 90), -1)
    return img


CACHE = Path.home() / ".cache" / "vectorizer-fonts"
TTF_TEST = CACHE / "Cormorant_Garamond_500.ttf"


# ── colocación (port verificado de scratch_perfect.py) ──────────────

def test_common_scale_mediana():
    font_bboxes = [(0, 0, 100, 200), (0, 0, 100, 100), (0, -50, 100, 150)]
    glyph_boxes = [(0, 0, 10, 30), (20, 0, 30, 20), (40, 0, 50, 30)]
    s = recompose_core.common_scale(font_bboxes, glyph_boxes)
    # ratios: 30/200=0.15, 20/100=0.20, 30/200=0.15 → mediana 0.15
    assert abs(s - 0.15) < 1e-9


def test_glyph_transform_alinea_centro_y_fondo():
    """El bbox renderizado debe calzar centro-x y fondo del box original
    (overshoot incluido) — la verificación 0.0px del prototipo, como assert."""
    fb = (10, -20, 110, 180)        # font units, y-up
    gb = (100, 50, 160, 110)        # imagen, y-down
    s = 0.3
    tr = recompose_core.glyph_transform(fb, gb, s)
    tx = float(tr.split("(")[1].split()[0])
    ty = float(tr.split("(")[1].split(")")[0].split()[1])
    # bbox renderizado: x ∈ [tx+s*xmin, tx+s*xmax], y_bottom = ty - s*ymin
    cx_render = tx + s * (fb[0] + fb[2]) / 2.0
    assert abs(cx_render - (gb[0] + gb[2]) / 2.0) < 1e-6
    assert abs((ty - s * fb[1]) - gb[3]) < 1e-6


# ── compose_hybrid_svg (dueño del cableado) ─────────────────────────

@pytest.mark.skipif(not TTF_TEST.exists(), reason="TTF de caché no disponible")
def test_compose_hybrid_svg_region_type_estructura():
    """compose_hybrid_svg sobre una región type: SVG con grupos ink+type,
    conteo de glifos, bbox de máscara y provenance con sha. La byte-identidad
    contra el inline se verifica en Task 3 (gate de aceptación), no aquí."""
    img = _logo_sintetico()
    r = _region(text="abc", bbox=(50, 60, 250, 115), n_glyphs=3)
    res = recompose_core.compose_hybrid_svg(
        img, [r], {0: ("Cormorant Garamond", 500)}, [0],
        sigma=2.0, cache_dir=CACHE)
    root = ET.fromstring(res.svg_text)
    grupos = [g.get("class") for g in root if g.tag.endswith("g")]
    assert "ink" in grupos and "type" in grupos
    assert res.glyph_count == 3
    assert res.mask_boxes == [(50, 60, 250, 115)]
    assert res.provenance and "Cormorant Garamond:500 sha256:" in res.provenance[0]
    assert "TTF provenance" in res.svg_text


def test_compose_hybrid_svg_sin_regiones_solo_caligrafia():
    """recomp_idx vacío → SVG con solo el grupo ink (caligrafía), sin glifos."""
    img = _logo_sintetico()
    res = recompose_core.compose_hybrid_svg(
        img, [], {}, [], sigma=2.0, cache_dir=CACHE)
    assert res.glyph_count == 0 and res.mask_boxes == []
    assert res.provenance == []
    ET.fromstring(res.svg_text)
