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


# ═══════════════════════════════════════════════════════════════════
# DESCARGA VALIDADA (sin red: solo la validación; la descarga real
# la ejercita la corrida del spike)
# ═══════════════════════════════════════════════════════════════════

def test_validate_ttf_rejects_garbage(tmp_path):
    """Bytes que no son TTF → False (no se cachearía)."""
    bad = tmp_path / "fake.ttf"
    bad.write_bytes(b"<html>error page</html>" * 10)
    assert fi.validate_ttf(bad) is False


def test_validate_ttf_accepts_real_font(tmp_path):
    """Un TTF real del sistema pasa la validación."""
    import shutil
    real = tmp_path / "georgia.ttf"
    shutil.copy(WIN_FONTS / "georgia.ttf", real)
    assert fi.validate_ttf(real) is True


# ═══════════════════════════════════════════════════════════════════
# REGRESIÓN DEL NÚCLEO (recomendadas por el quality review de Task 1)
# ═══════════════════════════════════════════════════════════════════

def test_iou_centroid_invariants():
    """iou(a,a)=1.0; par de aspecto extremo queda en [0,1] sin crash."""
    rng = np.random.default_rng(3)
    a = rng.random((40, 25)) > 0.5
    a[0, 0] = True                                  # garantiza no-vacía
    assert fi._iou_centroid(a, a) == 1.0
    tall = np.ones((100, 3), dtype=bool)
    wide = np.ones((5, 80), dtype=bool)
    v = fi._iou_centroid(tall, wide)
    assert 0.0 <= v <= 1.0


def test_common_scale_penalizes_proportion_mismatch():
    """La conducta load-bearing del spike: estirar el crop 1.6x en x debe
    BAJAR el score de la fuente correcta (el factor común no lo esconde).
    Test que falsa, no que confirma (principio del spec)."""
    crop = _render_word_bgr("mente", WIN_FONTS / "georgia.ttf")
    glyphs = fi.segment_glyphs(crop)
    base = fi.match_candidate(glyphs, list("mente"), WIN_FONTS / "georgia.ttf")
    stretched = cv2.resize(crop, (int(crop.shape[1] * 1.6), crop.shape[0]),
                           interpolation=cv2.INTER_CUBIC)
    glyphs_s = fi.segment_glyphs(stretched)
    assert len(glyphs_s) == 5
    s = fi.match_candidate(glyphs_s, list("mente"), WIN_FONTS / "georgia.ttf")
    assert s < base - 0.1     # la distorsión se penaliza, no se normaliza


# ═══════════════════════════════════════════════════════════════════
# CLI Y REPORTE
# ═══════════════════════════════════════════════════════════════════

def test_cli_region_text_pairing():
    """Conteos N≠M de --region/--text → SystemExit con error claro."""
    import pytest
    parser = fi.build_parser()
    args = parser.parse_args(["x.png", "--region", "0,0,10,10",
                              "--region", "0,0,20,20", "--text", "ab"])
    with pytest.raises(SystemExit):
        fi.validate_args(args)


def test_ties_marked():
    """Candidatos a <0.03 del líder se marcan EMPATE (umbral del spec)."""
    ranked = [("A", 0.700), ("B", 0.680), ("C", 0.640)]
    ties = fi.tie_flags(ranked)
    assert ties == [False, True, False]   # B empata con A; C no


def test_pool_has_controls():
    """El pool incluye los 4 controles negativos (gate medible)."""
    assert set(fi.CONTROLES) == {"Roboto", "Montserrat", "Oswald", "Pacifico"}
    assert len(fi.SPIKE_POOL) == 20
    assert not set(fi.CONTROLES) & set(fi.SPIKE_POOL)


# ═══════════════════════════════════════════════════════════════════
# FASE A — FUSIÓN VERTICAL (spec: hecho runtime 5)
# ═══════════════════════════════════════════════════════════════════

def test_vertical_fusion_integrative():
    """'integrative' (11 letras, 2 íes con punto) → 11 glifos TRAS fusión."""
    crop = _render_word_bgr("integrative", WIN_FONTS / "georgia.ttf")
    assert len(fi.segment_glyphs_fused(crop)) == 11


def test_vertical_fusion_preserves_mente():
    """Sin puntos, la fusión no altera nada: 'mente' sigue siendo 5."""
    crop = _render_word_bgr("mente", WIN_FONTS / "georgia.ttf")
    assert len(fi.segment_glyphs_fused(crop)) == 5
