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
