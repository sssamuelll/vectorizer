"""Tests del spike A.0 — aproximación de fuentes.

El test de matching usa fuentes del sistema Windows (siempre presentes).
Nota del spec (hallazgo Null Vale): estas fixtures NO cubren la zona de
ruido serif-vs-serif — eso lo prueba el gate del spike sobre el logo real.
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest
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


# ═══════════════════════════════════════════════════════════════════
# FASE A — METADATA Y POOL (spec: hecho runtime 4, Title Case)
# ═══════════════════════════════════════════════════════════════════


def _fake_metadata(tmp_path):
    """Escribe un metadata.json mínimo y fresco en el cache dir."""
    meta = {"familyMetadataList": [
        {"family": "Roboto", "category": "Sans Serif", "popularity": 1},
        {"family": "Lora", "category": "Serif", "popularity": 2},
        {"family": "Oswald", "category": "Sans Serif", "popularity": 3},
        {"family": "Cormorant Garamond", "category": "Serif", "popularity": 4},
        {"family": "Pacifico", "category": "Handwriting", "popularity": 5},
        {"family": "Cinzel", "category": "Display", "popularity": 6},
    ]}
    (tmp_path / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    return tmp_path


def test_pool_from_metadata_respects_categories(tmp_path):
    """Pool default: Serif + Sans Serif + Display por popularidad. Handwriting fuera."""
    cache = _fake_metadata(tmp_path)
    pool = fi.build_pool(fi.fetch_metadata(cache), pool_size=60)
    assert pool == ["Roboto", "Lora", "Oswald", "Cormorant Garamond", "Cinzel"]
    assert "Pacifico" not in pool


def test_pool_category_filter_normalizes_title_case(tmp_path):
    """--category 'sans-serif' (input del usuario) matchea 'Sans Serif' (Title Case real)."""
    cache = _fake_metadata(tmp_path)
    pool = fi.build_pool(fi.fetch_metadata(cache), pool_size=60, category="sans-serif")
    assert pool == ["Roboto", "Oswald"]


def test_pool_size_caps(tmp_path):
    cache = _fake_metadata(tmp_path)
    assert len(fi.build_pool(fi.fetch_metadata(cache), pool_size=2)) == 2


@pytest.mark.network
def test_metadata_real_download(tmp_path):
    """Descarga real: >1500 familias, categorías Title Case presentes."""
    meta = fi.fetch_metadata(tmp_path)
    assert len(meta) > 1500
    cats = {m.get("category") for m in meta}
    assert {"Serif", "Sans Serif", "Display"} <= cats


# ═══════════════════════════════════════════════════════════════════
# FASE A — PROBING DE PESOS (spec: wght 300-700, registra el elegido)
# ═══════════════════════════════════════════════════════════════════

FAKE_CSS = """
@font-face {
  font-family: 'Demo';
  font-style: normal;
  font-weight: 300;
  src: url(https://fonts.gstatic.com/s/demo/v1/light.ttf) format('truetype');
}
@font-face {
  font-family: 'Demo';
  font-style: normal;
  font-weight: 700;
  src: url(https://fonts.gstatic.com/s/demo/v1/bold.ttf) format('truetype');
}
"""


def test_parse_weight_css():
    pairs = fi.parse_weight_css(FAKE_CSS)
    assert pairs == [(300, "https://fonts.gstatic.com/s/demo/v1/light.ttf"),
                     (700, "https://fonts.gstatic.com/s/demo/v1/bold.ttf")]


def test_parse_weight_css_skips_range_blocks():
    """Bloques de fuente variable 'font-weight: 300 700;' se saltan, no se malparsean."""
    css = FAKE_CSS + '''
@font-face {
  font-family: 'Var';
  font-weight: 300 700;
  src: url(https://fonts.gstatic.com/s/var/v1/var.ttf) format('truetype');
}
'''
    pairs = fi.parse_weight_css(css)
    assert (300, "https://fonts.gstatic.com/s/var/v1/var.ttf") not in pairs
    assert len(pairs) == 2     # solo los dos bloques estáticos del FAKE_CSS


def test_match_family_returns_score_weight_and_scale(tmp_path):
    """match_family con un solo TTF local (sin red): devuelve (score, wght, s)."""
    import shutil
    fam_dir = tmp_path
    shutil.copy(WIN_FONTS / "georgia.ttf", fam_dir / "Georgia_400.ttf")
    crop = _render_word_bgr("mente", WIN_FONTS / "georgia.ttf")
    glyphs = fi.segment_glyphs_fused(crop)
    result = fi.match_family_local(glyphs, list("mente"),
                                   [(400, fam_dir / "Georgia_400.ttf")])
    assert result is not None
    score, wght, scale = result
    assert wght == 400
    assert 0.5 < score <= 1.0
    assert scale > 0


@pytest.mark.network
def test_weight_probing_real_garalda(tmp_path):
    """Familias de eje completo Y de eje estrecho: ambas deben dar pesos.
    (El bug del rango 300..700 devolvía [] para Lora/EB Garamond.)"""
    for fam, min_expected in [("Cormorant Garamond", 3), ("Lora", 2),
                              ("EB Garamond", 2)]:
        weights = fi.download_family_weights(fam, tmp_path)
        assert len(weights) >= min_expected, f"{fam}: {weights}"
        assert all(p.exists() for _, p in weights)


# ═══════════════════════════════════════════════════════════════════
# FASE A — OCR Y REGIONES (spec: negociación de idioma, hechos 1-2)
# ═══════════════════════════════════════════════════════════════════

winocr_available = True
try:
    import winocr  # noqa: F401
except ImportError:
    winocr_available = False

needs_ocr = pytest.mark.skipif(not winocr_available, reason="winocr no instalado")


@needs_ocr
def test_negotiate_language_returns_available():
    lang = fi.negotiate_ocr_language()
    assert isinstance(lang, str) and len(lang) >= 2


@needs_ocr
def test_detect_regions_two_lines(tmp_path):
    """Dos líneas de texto → dos regiones con texto y bbox absolutas."""
    font = ImageFont.truetype(str(WIN_FONTS / "georgia.ttf"), 60)
    img = Image.new("L", (900, 260), 255)
    d = ImageDraw.Draw(img)
    d.text((40, 30), "mente sana", fill=0, font=font)
    d.text((40, 150), "cuerpo sano", fill=0, font=font)
    bgr = cv2.cvtColor(np.array(img), cv2.COLOR_GRAY2BGR)
    regions = fi.detect_regions(bgr)
    assert len(regions) == 2
    texts = [r["text"].lower() for r in regions]
    assert "mente" in texts[0] and "cuerpo" in texts[1]
    x0, y0, x1, y1 = regions[0]["bbox"]
    assert 0 <= x0 < x1 <= 900 and 0 <= y0 < y1 <= 260


# ═══════════════════════════════════════════════════════════════════
# FASE A — CLASIFICACIÓN ESCALAR (spec: score + banda + stats crudas)
# ═══════════════════════════════════════════════════════════════════

def test_classify_typeset_line_scores_type():
    """Línea renderizada con fuente → lado tipografía, con stats crudas."""
    crop = _render_word_bgr("mente sana", WIN_FONTS / "georgia.ttf")
    masks, boxes = fi.segment_glyphs_with_boxes(crop)
    c = fi.classify_region(masks, "mente sana", boxes=boxes)
    assert c["label"] == "type"
    assert c["baseline_mode"] == "absolute"
    assert 0.0 <= c["score"] <= 1.0


def test_classify_descenders_still_type():
    """Palabra CON descendentes y ascendentes ('juega bien') → type igual
    (el defecto estructural que motivó esta enmienda)."""
    crop = _render_word_bgr("juega bien", WIN_FONTS / "georgia.ttf")
    masks, boxes = fi.segment_glyphs_with_boxes(crop)
    c = fi.classify_region(masks, "juega bien", boxes=boxes)
    assert c["label"] == "type", c


def test_classify_jittered_glyphs_scores_handwriting_side():
    """Jitter vertical y de escala sobre cajas absolutas → score más bajo."""
    crop = _render_word_bgr("mente sana", WIN_FONTS / "georgia.ttf")
    masks, boxes = fi.segment_glyphs_with_boxes(crop)
    clean = fi.classify_region(masks, "mente sana", boxes=boxes)
    rng = np.random.default_rng(11)
    jit_boxes = []
    for (x0, y0, x1, y1) in boxes:
        dy = int(rng.uniform(-14, 14))
        sc = rng.uniform(0.7, 1.4)
        h = max(2, int((y1 - y0) * sc))
        jit_boxes.append((x0, y0 + dy, x1, y0 + dy + h))
    jit = fi.classify_region(masks, "mente sana", boxes=jit_boxes)
    assert jit["score"] < clean["score"]


# ═══════════════════════════════════════════════════════════════════
# FASE A — NOMINACIÓN API (opt-in, solo nomina, falla → lista vacía)
# ═══════════════════════════════════════════════════════════════════

def test_api_nomination_failure_returns_empty(monkeypatch):
    """Sin SDK / sin key / API caída → [] con warning, jamás crash."""
    import builtins
    real_import = builtins.__import__

    def no_anthropic(name, *a, **k):
        if name == "anthropic":
            raise ImportError("simulado")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_anthropic)
    assert fi.nominate_via_api([b"fakepng"], ["mente"]) == []


def test_merge_nominations_marks_and_prioritizes():
    pool = ["Lora", "Roboto"]
    merged, api_set = fi.merge_nominations(pool, ["Cormorant SC", "Lora"])
    assert merged[0] == "Cormorant SC"          # nominada primero
    assert merged.count("Lora") == 1            # sin duplicados
    assert api_set == {"Cormorant SC"}          # solo lo NUEVO se marca [API]


# ═══════════════════════════════════════════════════════════════════
# FASE A — RANKING V2, JSON DRAFT, PREVIEW, CLI V2
# ═══════════════════════════════════════════════════════════════════

def _local_pool_dir(tmp_path):
    """Pool local de 3 fuentes del sistema como (familia → [(400, path)])."""
    import shutil
    d = tmp_path / "fonts"; d.mkdir()
    fams = {}
    for fam, fname in [("Georgia", "georgia.ttf"), ("Times", "times.ttf"),
                       ("Arial", "arial.ttf")]:
        p = d / f"{fam}_400.ttf"
        shutil.copy(WIN_FONTS / fname, p)
        fams[fam] = [(400, p)]
    return fams


def test_rank_region_v2_structure(tmp_path):
    crop = _render_word_bgr("mente", WIN_FONTS / "georgia.ttf")
    glyphs = fi.segment_glyphs_fused(crop)
    rows = fi.rank_families(glyphs, list("mente"), _local_pool_dir(tmp_path),
                            api_set=set())
    assert rows[0]["family"] == "Georgia"
    r = rows[0]
    assert {"family", "overlap", "wght", "scale", "api"} <= set(r)
    assert 0.0 <= r["overlap"] <= 1.0 and r["wght"] == 400 and r["api"] is False


def test_json_draft_contract(tmp_path):
    """El JSON: bboxes absolutas, sin '%', deltas, empates, wght, scale."""
    crop = _render_word_bgr("mente", WIN_FONTS / "georgia.ttf")
    glyphs = fi.segment_glyphs_fused(crop)
    rows = fi.rank_families(glyphs, list("mente"), _local_pool_dir(tmp_path),
                            api_set=set())
    doc = fi.build_json_draft([{
        "bbox": (450, 600, 1050, 770), "text": "mente",
        "classification": {"label": "type", "score": 0.9,
                           "baseline_residual": 1.0, "height_var": 0.05,
                           "repeats_used": True},
        "rows": rows, "skipped": 0,
    }])
    s = json.dumps(doc, ensure_ascii=False)
    assert "%" not in s
    reg = doc["regions"][0]
    assert reg["bbox"] == [450, 600, 1050, 770]          # absolutas
    assert doc["draft"] is True                            # emisión draft, no contrato
    top = reg["candidates"][0]
    assert {"family", "overlap", "delta_to_next", "tie_with_leader",
            "wght", "scale", "api"} <= set(top)


def test_preview_strip_written(tmp_path):
    crop = _render_word_bgr("mente", WIN_FONTS / "georgia.ttf")
    glyphs = fi.segment_glyphs_fused(crop)
    fams = _local_pool_dir(tmp_path)            # deja Georgia_400.ttf en tmp_path/fonts
    rows = fi.rank_families(glyphs, list("mente"), fams, api_set=set())
    out = tmp_path / "prev.png"
    fi.write_preview(crop, "mente", rows[:3], out, cache_dir=tmp_path / "fonts")
    assert out.exists() and out.stat().st_size > 1000


def test_cli_v2_flags_parse():
    args = fi.build_parser().parse_args(
        ["x.png", "--pool", "40", "--category", "serif", "--api",
         "--json", "--preview"])
    assert args.pool == 40 and args.category == "serif"
    assert args.api is True and args.json is True and args.preview is True


def test_cli_manual_mode_still_works():
    args = fi.build_parser().parse_args(
        ["x.png", "--region", "0,0,9,9", "--text", "ab"])
    fi.validate_args(args)   # no SystemExit
