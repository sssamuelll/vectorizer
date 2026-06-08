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


def _logo_sintetico():
    """120x300: un 'trazo caligráfico' (curva) arriba + una 'palabra'
    (3 rectángulos) abajo."""
    img = np.full((120, 300, 3), 255, np.uint8)
    cv2.ellipse(img, (150, 30), (100, 15), 0, 0, 360, (60, 110, 90), 6)
    for x in (60, 130, 200):
        cv2.rectangle(img, (x, 70), (x + 40, 110), (60, 110, 90), -1)
    return img


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

ALLOWED_IMPORTS = {
    "recompose.py": {
        "fontid": {"analyze_regions", "CACHE_DIR_DEFAULT"},
        "vectorize": {"load_image_bgr", "count_effective_colors"},
    },
    "recompose_core.py": {
        "fontid": {"download_family_weights"},
        "vectorize": {"clean_binary_mask", "extract_stroke_color", "trace_contours"},
        "recompose": set(),   # el core JAMÁS importa del CLI (unidireccional)
    },
}


def _violaciones_de_superficie(filename, allow):
    import ast
    src = (Path(__file__).resolve().parent.parent / filename)
    tree = ast.parse(src.read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in allow:
            extra = {a.name for a in node.names} - allow[node.module]
            if extra:
                out.append(f"{filename}:{node.module}: {sorted(extra)}")
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name in allow:
                    out.append(f"{filename}: import {a.name} completo (prohibido)")
    return out


def test_superficie_de_imports_cerrada():
    """La superficie declarada en el spec, vigilada por AST en AMBOS archivos.
    Ampliar la lista exige editar el spec Y este test — a propósito."""
    violaciones = []
    for fname, allow in ALLOWED_IMPORTS.items():
        violaciones += _violaciones_de_superficie(fname, allow)
    assert not violaciones, f"superficie de import violada: {violaciones}"


def test_main_guard_ultima_sentencia():
    """Ley del repo (lección de fontid): if __name__ va al FINAL."""
    import ast
    src = (Path(__file__).resolve().parent.parent / "recompose.py")
    tree = ast.parse(src.read_text(encoding="utf-8"))
    ultimo = tree.body[-1]
    assert isinstance(ultimo, ast.If) and ultimo.test.left.id == "__name__"


# ── HF2: --font desacopla recomposición del ranking (offline sovereignty) ──

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
