"""Tests de recompose.py (Fase B v0.1 — replay puro)."""
import sys
from pathlib import Path

import numpy as np
import cv2
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import recompose
import fontid


def _region(text="mente", bbox=(10, 10, 100, 40), classification="type",
            score=0.9, n_glyphs=5, ranking=None):
    gw = (bbox[2] - bbox[0]) // max(n_glyphs, 1)
    boxes = [(bbox[0] + i * gw, bbox[1], bbox[0] + i * gw + gw - 2, bbox[3])
             for i in range(n_glyphs)]
    return fontid.RegionAnalysis(
        bbox=bbox, text=text, classification=classification,
        class_score=score, glyph_boxes=boxes,
        ranking=ranking or [], scale_factor=0.15)


def _rank(*tuples):
    return [fontid.RankEntry(f, w, s, t) for f, w, s, t in tuples]


# ── reglas de la clave --font (spec §5) ─────────────────────────────

def test_parse_font_arg_basico():
    assert recompose.parse_font_arg("mente=Nanum Myeongjo:400") == \
        ("mente", "Nanum Myeongjo", 400)


def test_parse_font_arg_indice():
    assert recompose.parse_font_arg("#2=Lora:500") == ("#2", "Lora", 500)


def test_parse_font_arg_invalido():
    with pytest.raises(ValueError):
        recompose.parse_font_arg("mente=SinPeso")
    with pytest.raises(ValueError):
        recompose.parse_font_arg("sin-igual")


def test_resolver_font_por_texto_normalizado():
    regs = [_region(text="MENTE  extra")]
    out = recompose.resolve_font_choices(["mente extra=Lora:500"], regs)
    assert out == {0: ("Lora", 500)}


def test_resolver_font_por_indice():
    regs = [_region(text="a"), _region(text="a")]
    out = recompose.resolve_font_choices(["#2=Lora:500"], regs)
    assert out == {1: ("Lora", 500)}


def test_resolver_font_no_match_es_error_duro():
    regs = [_region(text="mente")]
    with pytest.raises(recompose.FontKeyError) as e:
        recompose.resolve_font_choices(["otracosa=Lora:500"], regs)
    assert "mente" in str(e.value)      # lista las claves disponibles


# ── costura (spec §3/§6: el tercer clasificador, nombrado) ──────────

def test_costura_type_se_recompone():
    r = _region(classification="type", ranking=_rank(("Lora", 400, 0.8, False)))
    decision = recompose.seam_decision(r)
    assert decision.recompose is True


def test_costura_handwriting_se_vectoriza():
    r = _region(classification="handwriting", score=0.3)
    d = recompose.seam_decision(r)
    assert d.recompose is False and "handwriting" in d.reason


def test_costura_type_sin_ranking_se_vectoriza():
    """type pero conteo glifos≠chars (ranking vacío) → degradación POR
    REGIÓN con razón explícita (spec §7)."""
    r = _region(classification="type", ranking=[])
    d = recompose.seam_decision(r)
    assert d.recompose is False and "ranking" in d.reason


def test_reporte_costura_siempre_lista_todas(capsys):
    regs = [
        _region(text="mente", classification="type",
                ranking=_rank(("Lora", 400, 0.8, False))),
        _region(text="libre", classification="handwriting", score=0.2),
    ]
    decisions = [recompose.seam_decision(r) for r in regs]
    recompose.print_seam_report(regs, decisions)
    out = capsys.readouterr().out
    assert "mente" in out and "libre" in out
    assert "recompone" in out and "vectoriza" in out


# ── colocación (port verificado de scratch_perfect.py) ──────────────

def test_common_scale_mediana():
    font_bboxes = [(0, 0, 100, 200), (0, 0, 100, 100), (0, -50, 100, 150)]
    glyph_boxes = [(0, 0, 10, 30), (20, 0, 30, 20), (40, 0, 50, 30)]
    s = recompose.common_scale(font_bboxes, glyph_boxes)
    # ratios: 30/200=0.15, 20/100=0.20, 30/200=0.15 → mediana 0.15
    assert abs(s - 0.15) < 1e-9


def test_glyph_transform_alinea_centro_y_fondo():
    """El bbox renderizado debe calzar centro-x y fondo del box original
    (overshoot incluido) — la verificación 0.0px del prototipo, como assert."""
    fb = (10, -20, 110, 180)        # font units, y-up
    gb = (100, 50, 160, 110)        # imagen, y-down
    s = 0.3
    tr = recompose.glyph_transform(fb, gb, s)
    tx = float(tr.split("(")[1].split()[0])
    ty = float(tr.split("(")[1].split(")")[0].split()[1])
    # bbox renderizado: x ∈ [tx+s*xmin, tx+s*xmax], y_bottom = ty - s*ymin
    cx_render = tx + s * (fb[0] + fb[2]) / 2.0
    assert abs(cx_render - (gb[0] + gb[2]) / 2.0) < 1e-6
    assert abs((ty - s * fb[1]) - gb[3]) < 1e-6


CACHE = Path.home() / ".cache" / "vectorizer-fonts"
TTF_TEST = CACHE / "Cormorant_Garamond_500.ttf"


@pytest.mark.skipif(not TTF_TEST.exists(),
                    reason="TTF de caché no disponible (corre fontid primero)")
def test_region_glyph_paths_con_ttf_real():
    boxes = [(100 + i * 60, 50, 150 + i * 60, 110) for i in range(5)]
    pairs = recompose.region_glyph_paths(TTF_TEST, "mente", boxes)
    assert len(pairs) == 5
    for d, tr in pairs:
        assert d and tr.startswith("translate(")
