"""Tests de recompose_core.py (compose compartido)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import recompose_core


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
