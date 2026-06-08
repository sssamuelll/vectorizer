"""Tests de Fase 1 — pipeline de color (vtracer) + fix de alpha.

Fixtures sintéticas generadas in-test con numpy/cv2 (cero binarios commiteados).
"""
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import vectorize as vz


# ═══════════════════════════════════════════════════════════════════
# FIXTURES SINTÉTICAS
# ═══════════════════════════════════════════════════════════════════

def make_logo(path, size=400):
    """Logo sintético de 4 colores planos (fondo blanco + 3 figuras)."""
    img = np.full((size, size, 3), 255, np.uint8)
    cv2.rectangle(img, (40, 40), (200, 200), (60, 60, 230), -1)    # rojo
    cv2.rectangle(img, (220, 80), (360, 320), (230, 120, 40), -1)  # azul
    cv2.circle(img, (200, 300), 70, (80, 180, 60), -1)             # verde
    cv2.imwrite(str(path), img)
    return path


def make_gradient(path, size=256):
    """Gradiente diagonal full-color — sensible a la inicialización del
    k-means (bajo RANDOM_CENTERS el conteo oscila; con el régimen
    determinista no debe oscilar jamás)."""
    y, x = np.mgrid[0:size, 0:size]
    img = np.stack([x * 255 // size, y * 255 // size,
                    (x + y) * 255 // (2 * size)], axis=-1).astype(np.uint8)
    cv2.imwrite(str(path), img)
    return path


# ═══════════════════════════════════════════════════════════════════
# ALPHA (spec: "Política de alpha compartida")
# ═══════════════════════════════════════════════════════════════════

def test_alpha_composites_on_white(tmp_path):
    """PNG transparente compone sobre BLANCO, no sobre negro."""
    rgba = np.zeros((100, 100, 4), np.uint8)             # todo transparente
    rgba[30:70, 30:70] = (0, 0, 255, 255)                # cuadro rojo opaco
    p = tmp_path / "alpha.png"
    cv2.imwrite(str(p), rgba)
    img = vz.load_image_bgr(p)
    assert img.shape == (100, 100, 3)
    assert (img[0, 0] == [255, 255, 255]).all()          # fondo blanco
    assert (img[50, 50] == [0, 0, 255]).all()            # el cuadro sobrevive


def test_load_matches_imread_for_opaque_png(tmp_path):
    """Para imágenes sin alpha el resultado es idéntico a cv2.imread (sin regresión)."""
    p = make_logo(tmp_path / "logo.png")
    assert (vz.load_image_bgr(p) == cv2.imread(str(p))).all()


def test_load_returns_none_for_missing_file(tmp_path):
    assert vz.load_image_bgr(tmp_path / "nope.png") is None


# ═══════════════════════════════════════════════════════════════════
# WRAPPER VTRACER (spec: hechos runtime 2-4 — posicional-only)
# ═══════════════════════════════════════════════════════════════════

def test_vtracer_wrapper_returns_svg(tmp_path):
    """El wrapper convierte PNG bytes → SVG string, con params custom."""
    p = make_logo(tmp_path / "logo.png")
    ok, buf = cv2.imencode(".png", cv2.imread(str(p)))
    assert ok
    svg = vz._vtracer_convert(buf.tobytes(), filter_speckle=8,
                              color_precision=6, layer_difference=48,
                              corner_threshold=45)
    assert "<svg" in svg
    assert "</svg>" in svg


# ═══════════════════════════════════════════════════════════════════
# COLORES EFECTIVOS + PRESET (spec: determinismo obligatorio)
# ═══════════════════════════════════════════════════════════════════

def test_effective_colors_deterministic(tmp_path):
    """Misma imagen → mismo conteo, sin importar el estado global del RNG.

    Usa el gradiente (divergence-prone): bajo RANDOM_CENTERS el conteo
    oscila entre 15 y 16. La técnica de pre-seed inyecta estados de RNG
    distintos ANTES de cada llamada; si count_effective_colors reimpone su
    propia semilla (régimen determinista), todos los resultados coinciden.
    Si se quita cv2.setRNGSeed o se cambia a RANDOM_CENTERS, los distintos
    pre-seeds producen resultados distintos y el assert falla de forma
    determinista (no estocástica). Verificado empíricamente: seeds 0-9
    producen al menos dos valores distintos bajo el régimen saboteado."""
    p = make_gradient(tmp_path / "grad.png")
    img = cv2.imread(str(p))
    # Inyectar 10 estados de RNG distintos antes de cada llamada.
    # Con el régimen correcto, count_effective_colors override la semilla →
    # todos los resultados son idénticos.
    pre_seeds = list(range(10))
    runs = []
    for s in pre_seeds:
        cv2.setRNGSeed(s)
        runs.append(vz.count_effective_colors(img))
    assert len(set(runs)) == 1, (
        f"count_effective_colors no es determinista: resultados={runs}"
    )

    repo = Path(vz.__file__).resolve().parent
    code = (f"import sys; sys.path.insert(0, {str(repo)!r}); "
            f"import cv2, vectorize; "
            f"print(vectorize.count_effective_colors(cv2.imread({str(p)!r})))")
    outs = set()
    for _ in range(2):
        r = subprocess.run([sys.executable, "-c", code],
                           capture_output=True, text=True, check=True)
        outs.add(r.stdout.strip())
    assert len(outs) == 1
    assert int(outs.pop()) == runs[0]


def test_preset_choice_logo_vs_photo(tmp_path):
    """≤12 colores efectivos → logo; ruido full-color → photo."""
    logo = cv2.imread(str(make_logo(tmp_path / "logo.png")))
    assert vz.choose_preset(logo) == "logo"
    rng = np.random.default_rng(7)
    noise = rng.integers(0, 256, (256, 256, 3), dtype=np.uint8)
    assert vz.choose_preset(noise) == "photo"


def test_preset_choice_deterministic(tmp_path):
    """Misma imagen → mismo conteo y mismo preset siempre (fixture divergence-prone).

    Pre-seed technique: inyecta estados distintos del RNG global antes de
    cada llamada para garantizar que el test falla bajo sabotaje.
    Verifica tanto el conteo numérico (más sensible) como el preset string."""
    img = cv2.imread(str(make_gradient(tmp_path / "grad.png")))
    counts = []
    for s in range(10):
        cv2.setRNGSeed(s)
        counts.append(vz.count_effective_colors(img))
    assert len(set(counts)) == 1, (
        f"count_effective_colors no es determinista: conteos={counts}"
    )
    # El preset string también debe ser consistente
    cv2.setRNGSeed(0)
    assert len({vz.choose_preset(img) for _ in range(3)}) == 1


# ═══════════════════════════════════════════════════════════════════
# PIPELINE COLOR END-TO-END (spec: Componente vectorize_color)
# ═══════════════════════════════════════════════════════════════════

def _path_fills(svg_file):
    """Colores de fill presentes, robusto: atributo `fill` O `style`
    (sin acoplarse a cómo vtracer codifique el color)."""
    root = ET.parse(svg_file).getroot()
    fills = set()
    for el in root.iter():
        f = (el.get("fill") or "").strip().lower()
        if f.startswith("#"):
            fills.add(f)
        for part in (el.get("style") or "").split(";"):
            if part.strip().lower().startswith("fill:"):
                fills.add(part.split(":", 1)[1].strip().lower())
    return fills


def test_vectorize_color_4color_logo(tmp_path):
    """Logo de 4 colores → XML válido, ≥3 fills distintos, dims correctas."""
    p = make_logo(tmp_path / "logo.png")
    out = vz.vectorize_color(p, output_path=tmp_path / "logo.svg")
    root = ET.parse(out).getroot()                 # parsea = XML válido
    assert root.get("width") == "400"
    assert root.get("height") == "400"
    assert root.get("viewBox") == "0 0 400 400"
    assert len(_path_fills(out)) >= 3


def test_vectorize_color_resizes_but_keeps_dims(tmp_path):
    """Imagen >1200px: viewBox en dims de trabajo, width/height originales."""
    img = np.full((1600, 800, 3), 255, np.uint8)
    cv2.rectangle(img, (100, 100), (700, 1500), (200, 80, 30), -1)
    p = tmp_path / "big.png"
    cv2.imwrite(str(p), img)
    out = vz.vectorize_color(p, output_path=tmp_path / "big.svg")
    root = ET.parse(out).getroot()
    assert root.get("width") == "800"
    assert root.get("height") == "1600"
    assert root.get("viewBox") == "0 0 600 1200"   # 1200/1600 = 0.75


def test_vectorize_color_no_ns0_pollution(tmp_path):
    """register_namespace evita prefijos ns0: en el roundtrip (hecho runtime 7)."""
    p = make_logo(tmp_path / "logo.png")
    out = vz.vectorize_color(p, output_path=tmp_path / "logo.svg")
    assert "ns0:" not in Path(out).read_text(encoding="utf-8")


def test_vectorize_color_unreadable_raises(tmp_path):
    """Imagen ilegible → ValueError (igual que el pipeline handwriting)."""
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"notapng" * 16)
    with pytest.raises(ValueError):
        vz.vectorize_color(bad, output_path=tmp_path / "bad.svg")


# ═══════════════════════════════════════════════════════════════════
# CLI (spec: default intacto + política de flags fuera de modo)
# ═══════════════════════════════════════════════════════════════════

def test_cli_default_mode_is_contour():
    """El default del CLI sigue siendo contour (test explícito del spec)."""
    args = vz.build_parser().parse_args(["x.png"])
    assert args.mode == "contour"


def test_cli_accepts_color_mode_and_flags():
    args = vz.build_parser().parse_args(
        ["x.png", "--mode", "color", "--preset", "logo",
         "--colors", "7", "--speckle", "10", "--layer-diff", "32",
         "--corner", "50", "--path-precision", "2", "--max-dim", "800"])
    assert args.mode == "color"
    assert args.preset == "logo"
    assert args.colors == 7
    assert args.speckle == 10
    assert args.layer_diff == 32
    assert args.corner == 50
    assert args.path_precision == 2
    assert args.max_dim == 800


def test_inert_handwriting_flag_warns_in_color_mode(capsys):
    args = vz.build_parser().parse_args(["x.png", "--mode", "color", "--rdp", "2.0"])
    vz.warn_inert_flags(args)
    assert "--rdp" in capsys.readouterr().out


def test_inert_color_flag_warns_in_contour_mode(capsys):
    args = vz.build_parser().parse_args(["x.png", "--speckle", "10"])
    vz.warn_inert_flags(args)
    assert "--speckle" in capsys.readouterr().out


# ═══════════════════════════════════════════════════════════════════
# ── filtro sigma (Fase B: --contour-sigma) ──────────────────────────
# ═══════════════════════════════════════════════════════════════════

def _circle_binary(noise_seed=None):
    """Círculo binario 200x200; con seed, borde con ruido de ±1px."""
    img = np.zeros((200, 200), np.uint8)
    cv2.circle(img, (100, 100), 60, 255, -1)
    if noise_seed is not None:
        rng = np.random.default_rng(noise_seed)
        contours, _ = cv2.findContours(img, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_NONE)
        for pt in contours[0].reshape(-1, 2)[::3]:
            dx, dy = rng.integers(-1, 2, 2)
            cv2.circle(img, (int(pt[0] + dx), int(pt[1] + dy)), 1, 255, -1)
    return img


def test_sigma_cero_output_identico():
    """default y sigma=0.0 explícito toman el mismo passthrough — la firma
    nueva no altera a los llamadores existentes."""
    binary = _circle_binary(noise_seed=7)
    antes = vz.trace_contours(binary, rdp_eps=0.8, chaikin_iter=2)
    despues = vz.trace_contours(binary, rdp_eps=0.8, chaikin_iter=2,
                                       sigma=0.0)
    assert antes == despues


def test_sigma_reduce_vertices():
    """sigma=2 sobre borde ruidoso produce paths con menos segmentos C
    (el filtro mata el ruido de píxel antes del RDP)."""
    binary = _circle_binary(noise_seed=7)
    sin = vz.trace_contours(binary, rdp_eps=0.8, chaikin_iter=2)
    con = vz.trace_contours(binary, rdp_eps=0.8, chaikin_iter=2,
                                   sigma=2.0)
    assert sum(d.count("C") for d in con) < sum(d.count("C") for d in sin)


def test_sigma_es_determinista():
    binary = _circle_binary(noise_seed=7)
    a = vz.trace_contours(binary, rdp_eps=0.8, chaikin_iter=2, sigma=2.0)
    b = vz.trace_contours(binary, rdp_eps=0.8, chaikin_iter=2, sigma=2.0)
    assert a == b


def test_gauss_filter_closed_preserva_forma():
    """El filtro circular sobre un cuadrado no colapsa el contorno:
    mismo número de puntos, centroide estable (<0.5px)."""
    pts = np.array([[float(x), 0.0] for x in range(50)] +
                   [[49.0, float(y)] for y in range(50)] +
                   [[float(x), 49.0] for x in range(49, -1, -1)] +
                   [[0.0, float(y)] for y in range(49, -1, -1)])
    out = vz._gauss_filter_closed(pts, sigma=2.0)
    assert out.shape == pts.shape
    assert np.linalg.norm(out.mean(axis=0) - pts.mean(axis=0)) < 0.5


def test_gauss_filter_contorno_corto_passthrough():
    """Contorno con 8<=n<=3*sigma NO crashea: passthrough (radius >= n)."""
    pts = np.arange(16, dtype=np.float64).reshape(8, 2)
    out = vz._gauss_filter_closed(pts, sigma=3.0)
    assert np.array_equal(out, pts)


def test_no_warning_when_flags_match_mode(capsys):
    args = vz.build_parser().parse_args(["x.png", "--mode", "color", "--speckle", "10"])
    vz.warn_inert_flags(args)
    assert "[WARN]" not in capsys.readouterr().out


# ═══════════════════════════════════════════════════════════════════
# MODO DIRECTORIO (spec: batch continúa, resumen nuevo)
# ═══════════════════════════════════════════════════════════════════

def test_batch_continues_after_corrupt_file(tmp_path, monkeypatch, capsys):
    """'bad.png' (bytes corruptos, ordena primero) no detiene el batch:
    'good.png' se procesa igual y el resumen cuenta el fallo."""
    (tmp_path / "bad.png").write_bytes(b"notapng" * 16)
    make_logo(tmp_path / "good.png")
    monkeypatch.setattr(sys, "argv",
                        ["vectorize.py", str(tmp_path), "--mode", "color"])
    vz.main()
    assert (tmp_path / "svg_output" / "good.svg").exists()
    out = capsys.readouterr().out
    assert "1 OK" in out
    assert "1 fallos" in out


# ═══════════════════════════════════════════════════════════════════
# ── CLI: --contour-sigma (Task 3) ──────────────────────────────────
# ═══════════════════════════════════════════════════════════════════

def test_cli_contour_sigma_default_cero():
    args = vz.build_parser().parse_args(["x.png"])
    assert args.contour_sigma == 0.0


def test_contour_sigma_inerte_en_modo_color(capsys):
    args = vz.build_parser().parse_args(
        ["x.png", "--mode", "color", "--contour-sigma", "2"])
    vz.warn_inert_flags(args)
    assert "--contour-sigma no aplica" in capsys.readouterr().out


def test_vectorize_acepta_contour_sigma(tmp_path):
    """vectorize() acepta contour_sigma y produce SVG válido."""
    img = np.full((120, 120, 3), 255, np.uint8)
    cv2.circle(img, (60, 60), 35, (40, 40, 40), -1)
    src = tmp_path / "in.png"
    cv2.imwrite(str(src), img)
    out = vz.vectorize(str(src), output_path=str(tmp_path / "o.svg"),
                       contour_sigma=2.0)
    root = ET.parse(out).getroot()
    assert root.tag.endswith("svg")


# ═══════════════════════════════════════════════════════════════════
# load_image_bgr_from_bytes — byte-identidad path vs bytes
# ═══════════════════════════════════════════════════════════════════

def test_load_from_bytes_igual_que_path(tmp_path):
    img = np.full((40, 60, 3), 200, np.uint8)
    img[10:20, 10:20] = (30, 60, 90)
    p = tmp_path / "x.png"
    cv2.imwrite(str(p), img)
    a = vz.load_image_bgr(p)
    b = vz.load_image_bgr_from_bytes(p.read_bytes())
    assert np.array_equal(a, b)


def test_load_from_bytes_png_alpha(tmp_path):
    """Política de alpha idéntica entre path y bytes (el caso que el draft tenía mal)."""
    bgra = np.zeros((20, 20, 4), np.uint8)
    bgra[..., :3] = (40, 80, 120)
    bgra[..., 3] = 128                     # semi-transparente → compone sobre blanco
    p = tmp_path / "a.png"
    cv2.imwrite(str(p), bgra)
    assert np.array_equal(vz.load_image_bgr(p),
                          vz.load_image_bgr_from_bytes(p.read_bytes()))


def test_load_from_bytes_jpeg_igual_que_path(tmp_path):
    """JPEG (el formato del asset de aceptación): path↔bytes byte-idéntico."""
    img = np.full((48, 64, 3), 180, np.uint8)
    img[12:24, 16:40] = (40, 70, 110)
    p = tmp_path / "x.jpg"
    cv2.imwrite(str(p), img)
    assert np.array_equal(vz.load_image_bgr(p),
                          vz.load_image_bgr_from_bytes(p.read_bytes()))


def test_load_from_bytes_vacio_o_none_es_none():
    """Parte de upload vacía/None → None, no excepción (imdecode asierta sobre
    buffer vacío; el guard lo filtra antes)."""
    assert vz.load_image_bgr_from_bytes(b"") is None
    assert vz.load_image_bgr_from_bytes(None) is None
    assert vz.load_image_bgr_from_bytes(b"no soy una imagen") is None
