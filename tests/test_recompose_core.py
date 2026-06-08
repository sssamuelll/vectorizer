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


def _rank(*tuples):
    return [fontid.RankEntry(f, w, s, t) for f, w, s, t in tuples]


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


# ── costura (spec §3/§6: el tercer clasificador, nombrado) ──────────

def test_costura_type_se_recompone():
    r = _region(classification="type", ranking=_rank(("Lora", 400, 0.8, False)))
    decision = recompose_core.seam_decision(r)
    assert decision.recompose is True


def test_costura_handwriting_se_vectoriza():
    r = _region(classification="handwriting", score=0.3)
    d = recompose_core.seam_decision(r)
    assert d.recompose is False and "handwriting" in d.reason


def test_costura_type_sin_ranking_se_vectoriza():
    """type pero conteo glifos≠chars (ranking vacío) → degradación POR
    REGIÓN con razón explícita (spec §7)."""
    r = _region(classification="type", ranking=[])
    d = recompose_core.seam_decision(r)
    assert d.recompose is False and "ranking" in d.reason


def test_seam_type_con_font_recompone_sin_ranking():
    """has_font=True fuerza recomposición aunque ranking esté vacío."""
    r = _region(classification="type", ranking=[])
    assert recompose_core.seam_decision(r, has_font=True).recompose is True


# ── colocación (port verificado de scratch_perfect.py) ──────────────

@pytest.mark.skipif(not TTF_TEST.exists(),
                    reason="TTF de caché no disponible (corre fontid primero)")
def test_region_glyph_paths_con_ttf_real():
    boxes = [(100 + i * 60, 50, 150 + i * 60, 110) for i in range(5)]
    pairs = recompose_core.region_glyph_paths(TTF_TEST, "mente", boxes,
                                              "Cormorant Garamond")
    assert len(pairs) == 5
    for d, tr in pairs:
        assert d and tr.startswith("translate(")


@pytest.mark.skipif(not TTF_TEST.exists(),
                    reason="TTF de caché no disponible")
def test_region_glyph_paths_char_sin_glifo(tmp_path):
    """Un char fuera del cmap → FontKeyError nombrando el char, no KeyError crudo."""
    with pytest.raises(recompose_core.FontKeyError) as e:
        recompose_core.region_glyph_paths(TTF_TEST, "中", [(0, 0, 50, 60)],
                                          "Cormorant Garamond")
    assert "中" in str(e.value)


def test_region_glyph_paths_ttf_corrupto(tmp_path):
    """TTF basura → FontKeyError, no TTLibError crudo."""
    bad = tmp_path / "Basura_400.ttf"
    bad.write_bytes(b"no soy una fuente")
    with pytest.raises(recompose_core.FontKeyError):
        recompose_core.region_glyph_paths(bad, "a", [(0, 0, 50, 60)], "Basura")


# ── resolución de TTF (spec §5: cualquier familia GF, on-demand) ────

def test_resolve_ttf_cache_hit(tmp_path):
    (tmp_path / "Mi_Fuente_400.ttf").write_bytes(b"x")
    p = recompose_core.resolve_ttf("Mi Fuente", 400, tmp_path)
    assert p.name == "Mi_Fuente_400.ttf"


def test_resolve_ttf_descarga_on_demand(tmp_path, monkeypatch):
    target = tmp_path / "Otra_500.ttf"
    monkeypatch.setattr(recompose_core, "download_family_weights",
                        lambda fam, cd: [(400, tmp_path / "Otra_400.ttf"),
                                         (500, target)])
    assert recompose_core.resolve_ttf("Otra", 500, tmp_path) == target


def test_resolve_ttf_peso_inexistente_error_duro(tmp_path, monkeypatch):
    """--font explícito con peso no disponible: JAMÁS sustituir la
    decisión del ojo en silencio (spec §7)."""
    monkeypatch.setattr(recompose_core, "download_family_weights",
                        lambda fam, cd: [(400, tmp_path / "Otra_400.ttf")])
    with pytest.raises(recompose_core.FontKeyError) as e:
        recompose_core.resolve_ttf("Otra", 900, tmp_path)
    assert "900" in str(e.value) and "400" in str(e.value)


def test_resolve_ttf_rechaza_familia_con_ruta(tmp_path, monkeypatch):
    """Cache-key traversal: familia con / \\ o .. rechazada ANTES de
    intentar download."""
    # Mock que vería se llama — si se llama, el test falla.
    calls = []
    monkeypatch.setattr(recompose_core, "download_family_weights",
                        lambda fam, cd: (calls.append(fam), [])[1])
    for malo in ("../evil", "a/b", "a\\b"):
        with pytest.raises(recompose_core.FontKeyError):
            recompose_core.resolve_ttf(malo, 400, tmp_path)
        # Verificar que download NO se llamó.
        assert malo not in calls, \
            f"download_family_weights se llamó con {malo!r} — validación inefectiva"


# ── caligrafía + composición ────────────────────────────────────────

def test_calligraphy_paths_excluye_regiones_enmascaradas():
    img = _logo_sintetico()
    todas = recompose_core.calligraphy_paths(img, [], sigma=2.0)
    sin_palabra = recompose_core.calligraphy_paths(img, [(50, 60, 250, 115)],
                                                   sigma=2.0)
    assert len(sin_palabra) < len(todas)
    assert len(sin_palabra) >= 1


def test_compose_svg_estructura():
    callig = ["M 10 10 L 50 10 L 50 50 Z"]
    glyphs = [("M 0 0 L 10 0 L 10 10 Z", "translate(5 5) scale(0.1 -0.1)")]
    svg_text = recompose_core.compose_svg(300, 120, "#86b0a3", callig, glyphs)
    root = ET.fromstring(svg_text)
    assert root.get("viewBox") == "0 0 300 120"
    grupos = [g.get("class") for g in root
              if g.tag.endswith("g")]
    assert "ink" in grupos and "type" in grupos
    assert "ns0" not in svg_text        # ley del repo: sin pollution


def test_compose_svg_con_provenance():
    svg_text = recompose_core.compose_svg(
        100, 50, "#000", ["M 0 0 L 1 1 Z"],
        [("M 0 0 Z", "translate(0 0) scale(1 -1)")],
        provenance=["Fam A:400 sha256:abcd1234"])
    assert "TTF provenance" in svg_text and "abcd1234" in svg_text
    ET.fromstring(svg_text)          # sigue siendo XML válido
    assert "ns0" not in svg_text


# ── compose_hybrid_svg (dueño del cableado) ─────────────────────────

@pytest.mark.skipif(not TTF_TEST.exists(), reason="TTF de caché no disponible")
def test_compose_hybrid_svg_region_type_estructura():
    """compose_hybrid_svg sobre una región type: SVG con grupos ink+type,
    conteo de glifos, bbox de máscara y provenance con sha. La byte-identidad
    contra el inline es el gate de aceptación sobre el logo de Ale (Task 5), no aquí."""
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


# ── resolve_choices: la política empate>líder>error (extraída de main) ──

def test_resolve_choices_lider_sin_empate_rellena():
    r = _region(text="abc", classification="type",
                ranking=_rank(("Lora", 400, 0.80, False), ("PT Serif", 400, 0.60, False)))
    res = recompose_core.resolve_choices([r], {})
    assert res.recomp_idx == [0]
    assert res.effective == {0: ("Lora", 400)}    # líder rellenado
    assert res.pendientes == [] and res.ignoradas == []


def test_resolve_choices_empate_queda_pendiente():
    r = _region(text="mente", classification="type",
                ranking=_rank(("Cormorant Garamond", 500, 0.753, False),
                              ("Libre Baskerville", 400, 0.747, True)))
    res = recompose_core.resolve_choices([r], {})
    assert res.recomp_idx == [0]
    assert 0 not in res.effective                 # no se rellena el empate
    assert [i for i, _ in res.pendientes] == [0]


def test_resolve_choices_explicita_gana():
    r = _region(text="mente", classification="type",
                ranking=_rank(("Cormorant Garamond", 500, 0.753, False),
                              ("Libre Baskerville", 400, 0.747, True)))
    res = recompose_core.resolve_choices([r], {0: ("Nanum Myeongjo", 400)})
    assert res.effective == {0: ("Nanum Myeongjo", 400)}
    assert res.pendientes == []                   # con elección no hay pendiente


def test_resolve_choices_choice_sobre_handwriting_es_ignorada():
    r = _region(text="libre", classification="handwriting", score=0.2)
    res = recompose_core.resolve_choices([r], {0: ("Lora", 400)})
    assert res.recomp_idx == []                   # handwriting no recompone
    assert res.ignoradas == [0]                   # la elección queda registrada como ignorada
    assert 0 not in res.effective


def test_resolve_choices_type_sin_ranking_sin_font_no_recompone():
    r = _region(text="abc", classification="type", ranking=[])
    res = recompose_core.resolve_choices([r], {})
    assert res.recomp_idx == [] and res.pendientes == []


def test_resolve_choices_multiregion_indexa_correcto():
    """Lote mixto: los índices de recomp_idx/ignoradas/pendientes/effective son
    correctos a través de regiones distintas — blinda el contrato de índices del
    que depende la byte-identidad de main() (Task 2)."""
    r0 = _region(text="abc", classification="type",
                 ranking=_rank(("Lora", 400, 0.80, False), ("PT Serif", 400, 0.60, False)))
    r1 = _region(text="libre", classification="handwriting", score=0.2)
    r2 = _region(text="mente", classification="type",
                 ranking=_rank(("Cormorant Garamond", 500, 0.753, False),
                               ("Libre Baskerville", 400, 0.747, True)))
    res = recompose_core.resolve_choices([r0, r1, r2], {1: ("Lora", 400)})
    assert res.recomp_idx == [0, 2]           # r0 líder, r2 empate; r1 handwriting fuera
    assert res.ignoradas == [1]               # choice sobre handwriting
    assert [i for i, _ in res.pendientes] == [2]
    assert res.effective == {0: ("Lora", 400)}  # líder de r0; r2 pendiente; 1 excluida


# ── region_overlay_paths: la unidad por región compartida con el overlay (C0) ──

def test_region_overlay_paths_reusa_resolve_y_glyph_paths(monkeypatch):
    """region_overlay_paths = resolve_ttf + (quita espacios) + region_glyph_paths.
    Offline: espía las dos dependencias y verifica el cableado y los args exactos."""
    r = _region(text="ab c", n_glyphs=3)          # 3 chars sin-espacio, 3 boxes
    visto = {}

    def fake_glyph_paths(ttf, chars, boxes, family):
        visto["ttf"], visto["chars"] = ttf, chars
        visto["boxes"], visto["family"] = boxes, family
        return [("M0Z", "matrix(1)"), ("M1Z", "matrix(2)"), ("M2Z", "matrix(3)")]

    monkeypatch.setattr(recompose_core, "resolve_ttf",
                        lambda fam, w, cd: Path("/fake/Cormorant_500.ttf"))
    monkeypatch.setattr(recompose_core, "region_glyph_paths", fake_glyph_paths)

    pairs, ttf = recompose_core.region_overlay_paths(r, "Cormorant Garamond", 500, "/cache")
    assert ttf == Path("/fake/Cormorant_500.ttf")
    assert pairs == [("M0Z", "matrix(1)"), ("M1Z", "matrix(2)"), ("M2Z", "matrix(3)")]
    assert visto["chars"] == ["a", "b", "c"]       # el espacio se quitó (política única)
    assert visto["boxes"] == r.glyph_boxes
    assert visto["family"] == "Cormorant Garamond"
    assert visto["ttf"] == Path("/fake/Cormorant_500.ttf")


@pytest.mark.skipif(not TTF_TEST.exists(), reason="TTF de caché no disponible")
def test_region_overlay_paths_identico_a_compose_type():
    """LA prueba de fidelidad: los pairs de region_overlay_paths == los paths del
    <g class='type'> que compose_hybrid_svg produce para esa región+candidata.
    El ojo (overlay) juzga exactamente lo que se descarga (compose)."""
    img = _logo_sintetico()
    r = _region(text="abc", bbox=(50, 60, 250, 115), n_glyphs=3)
    pairs, _ = recompose_core.region_overlay_paths(r, "Cormorant Garamond", 500, CACHE)
    res = recompose_core.compose_hybrid_svg(
        img, [r], {0: ("Cormorant Garamond", 500)}, [0], sigma=2.0, cache_dir=CACHE)
    root = ET.fromstring(res.svg_text)
    type_g = next(g for g in root
                  if g.tag.endswith("g") and g.get("class") == "type")
    compose_pairs = [(p.get("d"), p.get("transform")) for p in type_g]
    assert pairs == compose_pairs and len(pairs) == 3
