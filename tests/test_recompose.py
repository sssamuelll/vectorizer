"""Tests de recompose.py (Fase B v0.1 — replay puro)."""
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import cv2
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import recompose
import recompose_core
import fontid


def _region(text="mente", bbox=(10, 10, 100, 40), classification="type",
            score=0.9, n_glyphs=5, ranking=None):
    gw = (bbox[2] - bbox[0]) // max(n_glyphs, 1)
    boxes = [(bbox[0] + i * gw, bbox[1], bbox[0] + i * gw + gw - 2, bbox[3])
             for i in range(n_glyphs)]
    return fontid.RegionAnalysis(
        bbox=bbox, text=text, classification=classification,
        class_score=score, glyph_boxes=boxes,
        ranking=ranking or [])


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
    pairs = recompose.region_glyph_paths(TTF_TEST, "mente", boxes,
                                         "Cormorant Garamond")
    assert len(pairs) == 5
    for d, tr in pairs:
        assert d and tr.startswith("translate(")


@pytest.mark.skipif(not TTF_TEST.exists(),
                    reason="TTF de caché no disponible")
def test_region_glyph_paths_char_sin_glifo(tmp_path):
    """Un char fuera del cmap → FontKeyError nombrando el char, no KeyError crudo."""
    with pytest.raises(recompose.FontKeyError) as e:
        recompose.region_glyph_paths(TTF_TEST, "中", [(0, 0, 50, 60)],
                                     "Cormorant Garamond")
    assert "中" in str(e.value)


def test_region_glyph_paths_ttf_corrupto(tmp_path):
    """TTF basura → FontKeyError, no TTLibError crudo."""
    bad = tmp_path / "Basura_400.ttf"
    bad.write_bytes(b"no soy una fuente")
    with pytest.raises(recompose.FontKeyError):
        recompose.region_glyph_paths(bad, "a", [(0, 0, 50, 60)], "Basura")


# ── resolución de TTF (spec §5: cualquier familia GF, on-demand) ────

def test_resolve_ttf_cache_hit(tmp_path):
    (tmp_path / "Mi_Fuente_400.ttf").write_bytes(b"x")
    p = recompose.resolve_ttf("Mi Fuente", 400, tmp_path)
    assert p.name == "Mi_Fuente_400.ttf"


def test_resolve_ttf_descarga_on_demand(tmp_path, monkeypatch):
    target = tmp_path / "Otra_500.ttf"
    monkeypatch.setattr(recompose_core, "download_family_weights",
                        lambda fam, cd: [(400, tmp_path / "Otra_400.ttf"),
                                         (500, target)])
    assert recompose.resolve_ttf("Otra", 500, tmp_path) == target


def test_resolve_ttf_peso_inexistente_error_duro(tmp_path, monkeypatch):
    """--font explícito con peso no disponible: JAMÁS sustituir la
    decisión del ojo en silencio (spec §7)."""
    monkeypatch.setattr(recompose_core, "download_family_weights",
                        lambda fam, cd: [(400, tmp_path / "Otra_400.ttf")])
    with pytest.raises(recompose.FontKeyError) as e:
        recompose.resolve_ttf("Otra", 900, tmp_path)
    assert "900" in str(e.value) and "400" in str(e.value)


def test_resolve_ttf_rechaza_familia_con_ruta(tmp_path, monkeypatch):
    """Cache-key traversal: familia con / \\ o .. rechazada ANTES de
    intentar download."""
    # Mock que vería se llama — si se llama, el test falla.
    calls = []
    monkeypatch.setattr(recompose_core, "download_family_weights",
                        lambda fam, cd: (calls.append(fam), [])[1])
    for malo in ("../evil", "a/b", "a\\b"):
        with pytest.raises(recompose.FontKeyError) as exc:
            recompose.resolve_ttf(malo, 400, tmp_path)
        # Verificar que download NO se llamó.
        assert malo not in calls, \
            f"download_family_weights se llamó con {malo!r} — validación inefectiva"


# ── caligrafía + composición ────────────────────────────────────────

def _logo_sintetico():
    """120x300: un 'trazo caligráfico' (curva) arriba + una 'palabra'
    (3 rectángulos) abajo."""
    img = np.full((120, 300, 3), 255, np.uint8)
    cv2.ellipse(img, (150, 30), (100, 15), 0, 0, 360, (60, 110, 90), 6)
    for x in (60, 130, 200):
        cv2.rectangle(img, (x, 70), (x + 40, 110), (60, 110, 90), -1)
    return img


def test_calligraphy_paths_excluye_regiones_enmascaradas():
    img = _logo_sintetico()
    todas = recompose.calligraphy_paths(img, [], sigma=2.0)
    sin_palabra = recompose.calligraphy_paths(img, [(50, 60, 250, 115)],
                                              sigma=2.0)
    assert len(sin_palabra) < len(todas)
    assert len(sin_palabra) >= 1


def test_compose_svg_estructura():
    callig = ["M 10 10 L 50 10 L 50 50 Z"]
    glyphs = [("M 0 0 L 10 0 L 10 10 Z", "translate(5 5) scale(0.1 -0.1)")]
    svg_text = recompose.compose_svg(300, 120, "#86b0a3", callig, glyphs)
    root = ET.fromstring(svg_text)
    assert root.get("viewBox") == "0 0 300 120"
    grupos = [g.get("class") for g in root
              if g.tag.endswith("g")]
    assert "ink" in grupos and "type" in grupos
    assert "ns0" not in svg_text        # ley del repo: sin pollution


def test_compose_svg_con_provenance():
    svg_text = recompose.compose_svg(
        100, 50, "#000", ["M 0 0 L 1 1 Z"],
        [("M 0 0 Z", "translate(0 0) scale(1 -1)")],
        provenance=["Fam A:400 sha256:abcd1234"])
    assert "TTF provenance" in svg_text and "abcd1234" in svg_text
    ET.fromstring(svg_text)          # sigue siendo XML válido
    assert "ns0" not in svg_text


# ── preview + comandos de corrección (spec §6) ──────────────────────

def test_correction_commands_eco_de_la_decision(capsys):
    r = _region(text="mente", classification="type", ranking=_rank(
        ("Nanum Myeongjo", 400, 0.76, False), ("Cormorant Garamond", 500, 0.75, True),
        ("Libre Baskerville", 400, 0.74, True), ("Lora", 400, 0.66, False),
        ("PT Serif", 400, 0.65, False)))
    recompose.print_correction_commands(
        "logo.jpeg", [r], {0: ("Nanum Myeongjo", 400)})
    out = capsys.readouterr().out
    assert 'usada: Nanum Myeongjo 400' in out
    # las 3 siguientes del ranking como alternativas, comando armado
    assert '--font "mente=Cormorant Garamond:500"' in out
    assert '--font "mente=Libre Baskerville:400"' in out
    assert '--font "mente=Lora:400"' in out
    assert "PT Serif" not in out


def test_write_preview_sin_resvg_no_revienta(tmp_path, monkeypatch):
    """resvg_py es opcional: sin él, el preview se omite con aviso y la
    función devuelve None (el SVG es el entregable; el preview es la
    superficie de juicio)."""
    monkeypatch.setattr(recompose, "_render_svg", lambda svg: None)
    img = _logo_sintetico()
    out = recompose.write_preview(img, "<svg/>", [], tmp_path / "p.png")
    assert out is None and not (tmp_path / "p.png").exists()


def test_write_preview_con_render(tmp_path, monkeypatch):
    img = _logo_sintetico()
    monkeypatch.setattr(recompose, "_render_svg",
                        lambda svg: np.full_like(img, 255))
    out = recompose.write_preview(img, "<svg/>", [(50, 60, 250, 115)],
                                  tmp_path / "p.png")
    assert out is not None and out.exists()
    loaded = cv2.imread(str(out))
    assert loaded.shape[1] > img.shape[1]     # lado a lado: más ancho


# ── main() y exit codes (spec §7) ───────────────────────────────────

def _main_con(monkeypatch, tmp_path, regions, argv_extra=()):
    img = _logo_sintetico()
    src = tmp_path / "logo.png"
    cv2.imwrite(str(src), img)
    monkeypatch.setattr(recompose, "analyze_regions",
                        lambda im, **kw: regions)
    monkeypatch.setattr(sys, "argv",
                        ["recompose.py", str(src), *argv_extra])
    with pytest.raises(SystemExit) as e:
        recompose.main()
    return e.value.code, src


def test_main_sin_regiones_exit_2(monkeypatch, tmp_path, capsys):
    code, src = _main_con(monkeypatch, tmp_path, [])
    assert code == recompose.EXIT_NADA_QUE_RECOMPONER
    assert not src.with_name("logo_recompuesto.svg").exists()
    assert "vectorize.py" in capsys.readouterr().out


def test_main_ninguna_supera_costura_exit_2(monkeypatch, tmp_path, capsys):
    regs = [_region(text="libre", classification="handwriting", score=0.2)]
    code, src = _main_con(monkeypatch, tmp_path, regs)
    assert code == recompose.EXIT_NADA_QUE_RECOMPONER
    assert "0.2" in capsys.readouterr().out      # scores en el aviso


def test_main_empate_sin_font_exit_3(monkeypatch, tmp_path, capsys):
    regs = [_region(text="mente", classification="type", ranking=_rank(
        ("Cormorant Garamond", 500, 0.753, False),
        ("Libre Baskerville", 400, 0.747, True)))]
    code, _ = _main_con(monkeypatch, tmp_path, regs)
    assert code == recompose.EXIT_EMPATE_PENDIENTE
    out = capsys.readouterr().out
    assert '--font "mente=Cormorant Garamond:500"' in out   # comando sugerido armado


def test_main_font_no_match_exit_4(monkeypatch, tmp_path):
    regs = [_region(text="mente", classification="type",
                    ranking=_rank(("Lora", 400, 0.8, False)))]
    code, _ = _main_con(monkeypatch, tmp_path, regs,
                        argv_extra=["--font", "zzz=Lora:400"])
    assert code == recompose.EXIT_FONT_KEY


def test_main_camino_feliz_sin_empate(monkeypatch, tmp_path, capsys):
    """Líder sin empate → no exige --font; produce SVG con grupos."""
    regs = [_region(text="abc", bbox=(50, 60, 250, 115), n_glyphs=3,
                    classification="type",
                    ranking=_rank(("Cormorant Garamond", 500, 0.8, False),
                                  ("Lora", 400, 0.7, False)))]
    cache = Path.home() / ".cache" / "vectorizer-fonts"
    if not (cache / "Cormorant_Garamond_500.ttf").exists():
        pytest.skip("TTF de caché no disponible")
    code, src = _main_con(monkeypatch, tmp_path, regs)
    assert code == 0
    svg = src.with_name("logo_recompuesto.svg")
    assert svg.exists()
    texto = svg.read_text(encoding="utf-8")
    assert 'class="ink"' in texto and 'class="type"' in texto
    assert "TTF provenance" in texto
    assert svg.with_name(svg.stem + "_preview.png").exists()
    assert "re-corridas" in capsys.readouterr().out


def test_main_font_a_region_no_recompuesta_avisa(monkeypatch, tmp_path, capsys):
    """--font sobre región handwriting: WARN a stderr, no silencio."""
    regs = [
        _region(text="abc", bbox=(50, 60, 250, 115), n_glyphs=3,
                classification="type",
                ranking=_rank(("Cormorant Garamond", 500, 0.8, False),
                              ("Lora", 400, 0.7, False))),
        _region(text="libre", classification="handwriting", score=0.2),
    ]
    cache = Path.home() / ".cache" / "vectorizer-fonts"
    if not (cache / "Cormorant_Garamond_500.ttf").exists():
        pytest.skip("TTF de caché no disponible")
    code, _ = _main_con(monkeypatch, tmp_path, regs,
                        argv_extra=["--font", "libre=Lora:400"])
    assert code == 0
    assert "ignorado" in capsys.readouterr().err


# ── frontera mecánica de imports (spec §4: el CI cierra, no la prosa) ──

ALLOWED_INTERNAL_IMPORTS = {
    "fontid": {"analyze_regions", "download_family_weights",
               "CACHE_DIR_DEFAULT"},
    "vectorize": {"load_image_bgr", "trace_contours",
                  "extract_stroke_color", "clean_binary_mask",
                  "count_effective_colors"},
}


def test_superficie_de_imports_cerrada():
    """La superficie declarada en el spec, vigilada por AST. Ampliar la
    lista exige editar el spec Y este test — a propósito."""
    import ast
    src = (Path(__file__).resolve().parent.parent / "recompose.py")
    tree = ast.parse(src.read_text(encoding="utf-8"))
    violaciones = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in ALLOWED_INTERNAL_IMPORTS:
            extra = ({a.name for a in node.names}
                     - ALLOWED_INTERNAL_IMPORTS[node.module])
            if extra:
                violaciones.append(f"{node.module}: {sorted(extra)}")
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name in ALLOWED_INTERNAL_IMPORTS:
                    violaciones.append(f"import {a.name} completo (prohibido)")
    assert not violaciones, f"superficie de import violada: {violaciones}"


def test_main_guard_ultima_sentencia():
    """Ley del repo (lección de fontid): if __name__ va al FINAL."""
    import ast
    src = (Path(__file__).resolve().parent.parent / "recompose.py")
    tree = ast.parse(src.read_text(encoding="utf-8"))
    ultimo = tree.body[-1]
    assert isinstance(ultimo, ast.If) and ultimo.test.left.id == "__name__"


# ── HF2: --font desacopla recomposición del ranking (offline sovereignty) ──

def test_seam_type_con_font_recompone_sin_ranking():
    """has_font=True fuerza recomposición aunque ranking esté vacío."""
    r = _region(classification="type", ranking=[])
    assert recompose.seam_decision(r, has_font=True).recompose is True


def test_main_type_sin_fuente_sin_font_exit2(monkeypatch, tmp_path, capsys):
    """type + sin ranking + sin --font → nada que recomponer (EXIT 2), reporta 'sin fuente'."""
    regs = [_region(text="abc", classification="type", ranking=[])]
    code, _ = _main_con(monkeypatch, tmp_path, regs)
    assert code == recompose.EXIT_NADA_QUE_RECOMPONER
    assert "sin fuente" in capsys.readouterr().out


def test_main_font_offline_recompone_sin_ranking(monkeypatch, tmp_path):
    """Red caída (ranking vacío) + --font explícito → recompone igual. Antes EXIT 2."""
    regs = [_region(text="abc", bbox=(50, 60, 250, 115), n_glyphs=3,
                    classification="type", ranking=[])]
    cache = Path.home() / ".cache" / "vectorizer-fonts"
    if not (cache / "Cormorant_Garamond_500.ttf").exists():
        pytest.skip("TTF de caché no disponible")
    code, src = _main_con(monkeypatch, tmp_path, regs,
                          argv_extra=["--font", "abc=Cormorant Garamond:500"])
    assert code == 0
    assert src.with_name("logo_recompuesto.svg").exists()


# ── HF4: aviso multicolor (spec §7, precondición una tinta) ──────────

def test_main_avisa_multicolor(monkeypatch, tmp_path, capsys):
    """Imagen con muchos colores → [WARN] a stderr, no aborta."""
    img = np.zeros((60, 240, 3), np.uint8)
    for i, col in enumerate([(200, 0, 0), (0, 200, 0), (0, 0, 200), (200, 200, 0),
                             (200, 0, 200), (0, 200, 200), (120, 60, 30), (30, 120, 200),
                             (90, 200, 90), (200, 90, 90), (40, 40, 200), (200, 200, 200),
                             (10, 80, 140), (140, 10, 80)]):
        img[:, i * 16:(i + 1) * 16] = col
    src = tmp_path / "multi.png"
    cv2.imwrite(str(src), img)
    monkeypatch.setattr(recompose, "analyze_regions", lambda im, **kw: [])
    monkeypatch.setattr(sys, "argv", ["recompose.py", str(src)])
    import pytest as _pt
    with _pt.raises(SystemExit):
        recompose.main()
    assert "colores efectivos" in capsys.readouterr().err
