"""Tests del spike A.0 — aproximación de fuentes.

El test de matching usa fuentes del sistema Windows (siempre presentes).
Nota del spec (hallazgo Null Vale): estas fixtures NO cubren la zona de
ruido serif-vs-serif — eso lo prueba el gate del spike sobre el logo real.
"""
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fontid as fi

WIN_FONTS = Path("C:/Windows/Fonts")


def _render_word_bgr(text, ttf_path, size=80):
    """Renderiza una palabra negra sobre blanco como imagen BGR (fixture)."""
    font = ImageFont.truetype(str(ttf_path), size)
    bbox = font.getbbox(text)
    img = Image.new("L", (bbox[2] - bbox[0] + 20, bbox[3] - bbox[1] + 20), 255)
    ImageDraw.Draw(img).text((10 - bbox[0], 10 - bbox[1]), text, fill=0, font=font)
    return cv2.cvtColor(np.array(img), cv2.COLOR_GRAY2BGR)


def test_segment_glyphs_counts_mente():
    """'mente' (sin puntos ni acentos) → exactamente 5 componentes."""
    crop = _render_word_bgr("mente", WIN_FONTS / "georgia.ttf")
    glyphs = fi.segment_glyphs(crop)
    assert len(glyphs) == 5


def test_matching_correct_font_wins():
    """Mini-pool de 3 fuentes del sistema: la fuente correcta gana el ranking."""
    crop = _render_word_bgr("mente", WIN_FONTS / "georgia.ttf")
    glyphs = fi.segment_glyphs(crop)
    chars = list("mente")
    scores = {}
    for name, fname in [("georgia", "georgia.ttf"),
                        ("times", "times.ttf"),
                        ("arial", "arial.ttf")]:
        scores[name] = fi.match_candidate(glyphs, chars, WIN_FONTS / fname)
    assert all(s is not None for s in scores.values())
    assert max(scores, key=scores.get) == "georgia"
    assert scores["georgia"] > scores["arial"]          # serif vs sans: holgura


def test_match_candidate_insufficient_glyphs():
    """Región con <2 glifos → None ('insuficiente para matching', spec)."""
    crop = _render_word_bgr("m", WIN_FONTS / "georgia.ttf")
    glyphs = fi.segment_glyphs(crop)
    assert fi.match_candidate(glyphs, ["m"], WIN_FONTS / "georgia.ttf") is None
