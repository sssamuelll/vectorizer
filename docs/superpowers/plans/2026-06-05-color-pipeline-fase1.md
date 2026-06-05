# Fase 1: Pipeline de Color (vtracer) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir a `vectorize.py` un pipeline de color opt-in (`--mode color`) basado en vtracer, con presets, fix de alpha compartido y tests — sin cambiar el comportamiento de ninguna invocación existente.

**Architecture:** Todo vive en `vectorize.py` (decisión de spec). Se añaden: un helper de carga con composición de alpha (compartido por ambos pipelines), un wrapper de vtracer que SIEMPRE invoca en forma 100% posicional (kwargs → SIGSEGV en el wheel cp314, verificado), análisis determinista de colores efectivos para elegir preset, `vectorize_color()` con post-proceso de SVG (añadir `viewBox`, restaurar dims originales, `register_namespace`), y CLI extendido con default intacto (`contour`).

**Tech Stack:** Python 3.14, OpenCV (cv2), numpy, vtracer 0.6.15 (wheel cp314-win_amd64), xml.etree.ElementTree, pytest.

**Spec:** `docs/superpowers/specs/2026-06-05-general-image-vectorizer-design.md` (v2, secciones "Fase 1", "Dependencias y hechos runtime verificados", "Manejo de errores", "Testing → Fase 1").

**⚠️ Regla no negociable del spec (hecho runtime 2-4):** jamás pasar keyword arguments a funciones de `vtracer` — el binding PyO3 del wheel cp314 produce `ACCESS_VIOLATION 0xC0000005` que mata el proceso sin excepción capturable. Toda invocación pasa por el wrapper `_vtracer_convert` (Task 2), que traduce a posicional completo.

---

## File Structure

| archivo | responsabilidad |
|---|---|
| `vectorize.py` (modificar) | Se añaden: sección 0 (helper de carga con alpha), sección 6.5 (pipeline color: wrapper vtracer, análisis de colores, presets, `vectorize_color`, post-proceso SVG), y CLI extendido (`build_parser`, `warn_inert_flags`, dispatch y resumen en `main`). Las secciones 1-6 existentes NO se tocan. |
| `tests/test_vectorize.py` (crear) | Tests pytest de Fase 1: alpha, wrapper, determinismo de preset, pipeline color end-to-end, resize, CLI, batch con corrupto, flags inertes. Fixtures sintéticas in-test (cero binarios commiteados). |
| `requirements.txt` (modificar) | `+vtracer>=0.6.15` con nota de plataforma, `+pytest` (dev). |
| `README.md` (modificar) | Modo `color`, presets, flags nuevos, contrato de salida, cambio de alpha declarado, peso de SVGs de fotos. |

Convención de tests: `tests/test_vectorize.py` importa el script con `sys.path.insert` (no hay paquete). Los tests que invocan vtracer requieren vtracer instalado (está en requirements).

---

### Task 1: Helper de carga con composición de alpha

El fix del spec ("Política de alpha compartida"): `cv2.imread` default descarta alpha → un PNG transparente entra con fondo negro. Un solo helper, usado por ambos pipelines.

**Files:**
- Create: `tests/test_vectorize.py`
- Modify: `vectorize.py` (nueva función tras los imports; reemplazo en `vectorize()` línea 372)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_vectorize.py`:

```python
"""Tests de Fase 1 — pipeline de color (vtracer) + fix de alpha.

Fixtures sintéticas generadas in-test con numpy/cv2 (cero binarios commiteados).
"""
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_vectorize.py -v`
Expected: 3 FAIL/ERROR with `AttributeError: module 'vectorize' has no attribute 'load_image_bgr'`

- [ ] **Step 3: Implement `load_image_bgr` in `vectorize.py`**

Insert after the imports block (after line 18, `import xml.etree.ElementTree as ET`):

```python
# ═══════════════════════════════════════════════════════════════════
# 0. CARGA DE IMAGEN (política de alpha compartida)
# ═══════════════════════════════════════════════════════════════════

def load_image_bgr(image_path):
    """Carga una imagen como BGR uint8, componiendo alpha sobre blanco.

    cv2.imread por defecto descarta el canal alpha: un PNG transparente
    entra con fondo negro basura. Aquí: IMREAD_UNCHANGED + composición
    sobre blanco. Una sola política para todos los pipelines.
    Devuelve None si la imagen no se puede cargar (igual que cv2.imread).
    """
    img = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
    if img is None:
        return None
    if img.dtype == np.uint16:                    # PNG de 16 bits → 8 bits
        img = (img // 257).astype(np.uint8)
    if img.ndim == 2:                             # escala de grises → BGR
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if img.shape[2] == 4:                         # BGRA → componer sobre blanco
        alpha = img[:, :, 3:4].astype(np.float64) / 255.0
        bgr = img[:, :, :3].astype(np.float64)
        return (bgr * alpha + 255.0 * (1.0 - alpha)).astype(np.uint8)
    return img
```

- [ ] **Step 4: Wire into the handwriting pipeline**

In `vectorize()`, replace line 372:

```python
    img = cv2.imread(str(image_path))
```

with:

```python
    img = load_image_bgr(image_path)
```

(El `if img is None: raise ValueError` de la línea siguiente queda igual.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_vectorize.py -v`
Expected: 3 PASS

- [ ] **Step 6: Smoke test — el pipeline handwriting sigue funcionando**

```powershell
python -c "
import numpy as np, cv2, tempfile, os
import vectorize as vz
d = tempfile.mkdtemp()
img = np.full((300, 300, 3), 255, np.uint8)
cv2.ellipse(img, (150, 150), (80, 40), 30, 0, 360, (40, 40, 40), 3)
p = os.path.join(d, 'trazo.png')
cv2.imwrite(p, img)
vz.vectorize(p)
print('smoke OK')
"
```

Expected: `[OK] SVG: ...trazo.svg` y `smoke OK`, sin tracebacks.

- [ ] **Step 7: Commit**

```bash
git add tests/test_vectorize.py vectorize.py
git commit -m "feat: shared alpha-compositing image loader (IMREAD_UNCHANGED + white)"
```

---

### Task 2: Wrapper posicional de vtracer

La regla no negociable: nuestro código habla con vtracer SOLO a través de esta función, que traduce parámetros nombrados (de nuestro lado, seguro) a la invocación 100% posicional (el único modo que no segfaultea).

**Files:**
- Modify: `vectorize.py` (nueva sección antes de la sección 7. PIPELINE)
- Test: `tests/test_vectorize.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_vectorize.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_vectorize.py::test_vtracer_wrapper_returns_svg -v`
Expected: FAIL with `AttributeError: module 'vectorize' has no attribute '_vtracer_convert'`

- [ ] **Step 3: Implement the wrapper**

Insert in `vectorize.py`, between section 6 (AGUJEROS) and section 7 (PIPELINE):

```python
# ═══════════════════════════════════════════════════════════════════
# 6.5. PIPELINE DE COLOR (vtracer)
# ═══════════════════════════════════════════════════════════════════

SVG_NS = "http://www.w3.org/2000/svg"


def _vtracer_convert(png_bytes,
                     colormode="color", hierarchical="stacked", mode="spline",
                     filter_speckle=4, color_precision=6, layer_difference=16,
                     corner_threshold=60, length_threshold=4.0,
                     max_iterations=10, splice_threshold=45, path_precision=3):
    """Única puerta hacia vtracer. Invoca SIEMPRE en forma 100% posicional.

    NUNCA pasar kwargs a vtracer: el binding PyO3 del wheel cp314 produce
    SIGSEGV (ACCESS_VIOLATION 0xC0000005) con cualquier keyword argument
    en Python 3.14 — mata el proceso sin excepción capturable.
    Verificado 2026-06-05 (spec, hechos runtime 2-4). Orden posicional:
    (img_bytes, img_format, colormode, hierarchical, mode, filter_speckle,
     color_precision, layer_difference, corner_threshold, length_threshold,
     max_iterations, splice_threshold, path_precision)
    """
    try:
        import vtracer
    except ImportError:
        raise RuntimeError(
            "El modo color requiere vtracer. Instala con: pip install vtracer"
        ) from None
    return vtracer.convert_raw_image_to_svg(
        png_bytes, "png", colormode, hierarchical, mode,
        filter_speckle, color_precision, layer_difference,
        corner_threshold, length_threshold, max_iterations,
        splice_threshold, path_precision,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_vectorize.py::test_vtracer_wrapper_returns_svg -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_vectorize.py vectorize.py
git commit -m "feat: vtracer wrapper with positional-only invocation (kwargs segfault on cp314)"
```

---

### Task 3: Análisis de colores efectivos + selección de preset

Determinismo obligatorio (spec, "Selección automática de preset"): semilla fija + `KMEANS_PP_CENTERS` + `attempts>=3`. Sin esto el conteo varía entre corridas (verificado runtime).

**Files:**
- Modify: `vectorize.py` (continuación de la sección 6.5)
- Test: `tests/test_vectorize.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_vectorize.py`:

```python
# ═══════════════════════════════════════════════════════════════════
# COLORES EFECTIVOS + PRESET (spec: determinismo obligatorio)
# ═══════════════════════════════════════════════════════════════════

def test_effective_colors_deterministic(tmp_path):
    """Misma imagen → mismo conteo en corridas repetidas."""
    img = cv2.imread(str(make_logo(tmp_path / "logo.png")))
    runs = [vz.count_effective_colors(img) for _ in range(3)]
    assert runs[0] == runs[1] == runs[2]


def test_preset_choice_logo_vs_photo(tmp_path):
    """≤12 colores efectivos → logo; ruido full-color → photo."""
    logo = cv2.imread(str(make_logo(tmp_path / "logo.png")))
    assert vz.choose_preset(logo) == "logo"
    rng = np.random.default_rng(7)
    noise = rng.integers(0, 256, (256, 256, 3), dtype=np.uint8)
    assert vz.choose_preset(noise) == "photo"


def test_preset_choice_deterministic(tmp_path):
    """Misma imagen → mismo preset siempre (test del grupo 'Preset determinista')."""
    img = cv2.imread(str(make_logo(tmp_path / "logo.png")))
    assert len({vz.choose_preset(img) for _ in range(3)}) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_vectorize.py -v -k "effective or preset_choice"`
Expected: 3 FAIL with `AttributeError` (`count_effective_colors` / `choose_preset` no existen)

- [ ] **Step 3: Implement**

Append to section 6.5 in `vectorize.py` (after `_vtracer_convert`):

```python
def count_effective_colors(img_bgr, k=16, coverage=0.95, max_side=256,
                           sample_px=10000, seed=42):
    """Cuenta colores efectivos: nº de clusters k-means (LAB) que cubren
    `coverage` de los píxeles, ordenados por población.

    Determinismo obligatorio (spec): semilla fija, KMEANS_PP_CENTERS y
    attempts=3 — con RANDOM_CENTERS el conteo varía entre corridas.
    k=16 para resolver el umbral de preset (12).
    """
    h, w = img_bgr.shape[:2]
    if max(h, w) > max_side:
        s = max_side / max(h, w)
        img_bgr = cv2.resize(img_bgr, (max(1, int(w * s)), max(1, int(h * s))),
                             interpolation=cv2.INTER_AREA)
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    pixels = lab.reshape(-1, 3).astype(np.float32)
    if len(pixels) > sample_px:
        rng = np.random.default_rng(seed)
        pixels = pixels[rng.choice(len(pixels), sample_px, replace=False)]
    k = min(k, len(pixels))
    cv2.setRNGSeed(seed)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.5)
    _, labels, _ = cv2.kmeans(pixels, k, None, criteria, 3,
                              cv2.KMEANS_PP_CENTERS)
    counts = np.sort(np.bincount(labels.flatten(), minlength=k))[::-1]
    cum = np.cumsum(counts) / counts.sum()
    return int(np.searchsorted(cum, coverage) + 1)


def choose_preset(img_bgr):
    """≤12 colores efectivos → logo; >12 → photo.

    `drawing` solo se activa manualmente (--preset drawing) — decisión
    intencional del spec: el conteo de color no separa de forma fiable
    una ilustración con gradientes de un logo o una foto.
    """
    n = count_effective_colors(img_bgr)
    preset = "logo" if n <= 12 else "photo"
    print(f"  [PRESET] {preset} ({n} colores efectivos)")
    return preset
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_vectorize.py -v -k "effective or preset_choice"`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_vectorize.py vectorize.py
git commit -m "feat: deterministic effective-color analysis and preset auto-selection"
```

---

### Task 4: `vectorize_color` end-to-end con post-proceso de SVG

El corazón de Fase 1. Post-proceso según hecho runtime 7: vtracer NO emite `viewBox` — se añade; `width`/`height` se reescriben a las dims originales; `register_namespace` ANTES de parsear o el roundtrip contamina con `ns0:`. Si el post-proceso falla → escribir tal cual CON warning (nunca silencio).

**Files:**
- Modify: `vectorize.py` (continuación de la sección 6.5)
- Test: `tests/test_vectorize.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_vectorize.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_vectorize.py -v -k "vectorize_color"`
Expected: 4 FAIL with `AttributeError: module 'vectorize' has no attribute 'vectorize_color'`

- [ ] **Step 3: Implement presets, post-proceso y `vectorize_color`**

Append to section 6.5 in `vectorize.py` (after `choose_preset`):

```python
COLOR_PRESETS = {
    # spec: tabla de presets. Comunes a los tres: mode=spline,
    # hierarchical=stacked, path_precision=3 (defaults del wrapper).
    "logo":    dict(filter_speckle=8, color_precision=6,
                    layer_difference=48, corner_threshold=45),
    "drawing": dict(filter_speckle=4, color_precision=7,
                    layer_difference=24, corner_threshold=60),
    "photo":   dict(filter_speckle=4, color_precision=8,
                    layer_difference=12, corner_threshold=60),
}


def _write_svg_scaled(svg_text, out_path, orig_w, orig_h, work_w, work_h):
    """Post-proceso del SVG de vtracer (spec, hecho runtime 7).

    vtracer emite el root SIN viewBox → se añade (dims de trabajo) y se
    reescriben width/height (dims originales) — la misma política de
    escala del pipeline handwriting. register_namespace ANTES de parsear
    o ElementTree contamina el roundtrip con prefijos ns0:.
    Si el post-proceso falla: se escribe tal cual CON warning (la
    degradación silenciosa era una contradicción del spec v1).
    """
    out_path = Path(out_path)
    try:
        ET.register_namespace("", SVG_NS)
        root = ET.fromstring(svg_text)
        root.set("width", str(orig_w))
        root.set("height", str(orig_h))
        root.set("viewBox", f"0 0 {work_w} {work_h}")
        ET.ElementTree(root).write(out_path, encoding="utf-8",
                                   xml_declaration=True)
    except ET.ParseError as e:
        print(f"  [WARN] Post-proceso del SVG falló ({e}); "
              f"se escribe sin escalar — dims de vtracer, no originales.")
        out_path.write_text(svg_text, encoding="utf-8")
    return out_path


def vectorize_color(image_path, output_path=None, preset=None, max_dim=1200,
                    **overrides):
    """Vectoriza una imagen a color con vtracer (logos, ilustraciones, fotos).

    preset:
      - None (default): se elige solo — ≤12 colores efectivos → logo, >12 → photo.
      - "logo" | "drawing" | "photo": explícito.
    max_dim: resize previo en memoria si el lado mayor lo supera (0 = sin resize).
    overrides: filter_speckle, color_precision, layer_difference,
               corner_threshold, path_precision — pisan el preset (None = no pisa).
    """
    img = load_image_bgr(image_path)
    if img is None:
        raise ValueError(f"No se pudo cargar: {image_path}")

    orig_h, orig_w = img.shape[:2]
    work = img
    if max_dim and max(orig_w, orig_h) > max_dim:
        s = max_dim / max(orig_w, orig_h)
        work = cv2.resize(img, (int(orig_w * s), int(orig_h * s)),
                          interpolation=cv2.INTER_AREA)
    work_h, work_w = work.shape[:2]

    if preset is None:
        preset = choose_preset(work)
    params = dict(COLOR_PRESETS[preset])
    params.update({k: v for k, v in overrides.items() if v is not None})

    ok, buf = cv2.imencode(".png", work)
    if not ok:
        raise ValueError(f"No se pudo codificar a PNG: {image_path}")
    svg_text = _vtracer_convert(buf.tobytes(), **params)

    out = Path(output_path) if output_path else Path(image_path).with_suffix(".svg")
    _write_svg_scaled(svg_text, out, orig_w, orig_h, work_w, work_h)

    print(f"  [OK] SVG: {out}")
    print(f"       Modo: color | Preset: {preset}")
    return out
```

Nota: `params.update(...)` con `_vtracer_convert(**params)` es seguro — son kwargs hacia NUESTRO wrapper Python; el wrapper es quien traduce a posicional hacia vtracer.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_vectorize.py -v -k "vectorize_color"`
Expected: 4 PASS

- [ ] **Step 5: Run the full suite (no regression)**

Run: `python -m pytest tests/test_vectorize.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add tests/test_vectorize.py vectorize.py
git commit -m "feat: vectorize_color pipeline with presets and SVG post-processing"
```

---

### Task 5: CLI — `build_parser`, flags nuevos, warnings de flags inertes, dispatch

El default NO cambia (`contour`). `--mode color` se añade. Flags fuera de su modo → warning, nunca silencio (spec, "Política de flags fuera de su modo"). `build_parser()` se extrae de `main()` para que el default sea testeable.

**Files:**
- Modify: `vectorize.py` (sección 8. MAIN — reescritura de `main()`, nuevas `build_parser` y `warn_inert_flags`; añadir `import sys` a los imports)
- Test: `tests/test_vectorize.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_vectorize.py`:

```python
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


def test_no_warning_when_flags_match_mode(capsys):
    args = vz.build_parser().parse_args(["x.png", "--mode", "color", "--speckle", "10"])
    vz.warn_inert_flags(args)
    assert "[WARN]" not in capsys.readouterr().out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_vectorize.py -v -k "cli or inert or no_warning"`
Expected: 5 FAIL with `AttributeError` (`build_parser` / `warn_inert_flags` no existen)

- [ ] **Step 3: Implement — add `import sys`, `build_parser`, `warn_inert_flags`, rewrite `main()`**

3a. In the imports block of `vectorize.py` (line 14-18), add `import sys`:

```python
import cv2
import numpy as np
from pathlib import Path
import argparse
import sys
import xml.etree.ElementTree as ET
```

3b. Replace the whole `main()` function (current lines 461-508) and add the two new functions before it, keeping the section banner `# 8. MAIN`:

```python
def build_parser():
    parser = argparse.ArgumentParser(
        description="Vectoriza imágenes a SVG: handwriting (contour/skeleton) "
                    "o color con vtracer (logos, ilustraciones, fotos)"
    )
    parser.add_argument("input", help="Imagen PNG/JPG o directorio")
    parser.add_argument("-o", "--output", help="SVG o directorio de salida")
    parser.add_argument("--mode", choices=("contour", "skeleton", "both", "color"),
                        default="contour",
                        help="contour=relleno fiel | skeleton=línea fina | "
                             "both=ambos | color=vtracer full-color")
    # flags handwriting (solo modos contour/skeleton/both)
    parser.add_argument("--blur", type=int, default=3)
    parser.add_argument("--rdp", type=float, default=1.0)
    parser.add_argument("--chaikin", type=int, default=2)
    parser.add_argument("--tension", type=float, default=0.5)
    parser.add_argument("--width", type=float, default=2.0,
                        help="Stroke width for skeleton mode")
    parser.add_argument("--color", default=None, help="Forzar color hex")
    parser.add_argument("--no-auto-color", action="store_true")
    # flags color (solo modo color)
    parser.add_argument("--preset", choices=("logo", "drawing", "photo"),
                        default=None,
                        help="Preset del modo color (default: auto por "
                             "colores efectivos; drawing solo manual)")
    parser.add_argument("--colors", type=int, default=None,
                        help="color_precision de vtracer")
    parser.add_argument("--speckle", type=int, default=None,
                        help="filter_speckle de vtracer")
    parser.add_argument("--layer-diff", type=int, default=None,
                        help="layer_difference de vtracer")
    parser.add_argument("--corner", type=int, default=None,
                        help="corner_threshold de vtracer")
    parser.add_argument("--path-precision", type=int, default=None,
                        help="Decimales de coordenadas en el SVG")
    parser.add_argument("--max-dim", type=int, default=1200,
                        help="Resize previo del modo color (0 = sin resize)")
    return parser


_HANDWRITING_FLAG_DEFAULTS = {
    "blur": 3, "rdp": 1.0, "chaikin": 2, "tension": 0.5,
    "width": 2.0, "color": None, "no_auto_color": False,
}
_COLOR_FLAG_DEFAULTS = {
    "preset": None, "colors": None, "speckle": None,
    "layer_diff": None, "corner": None, "path_precision": None,
    "max_dim": 1200,
}


def warn_inert_flags(args):
    """Avisa de flags que no aplican al modo activo (spec: nada se ignora
    en silencio). El flag inerte se reporta; no altera el resultado."""
    inert = (_HANDWRITING_FLAG_DEFAULTS if args.mode == "color"
             else _COLOR_FLAG_DEFAULTS)
    for name, default in inert.items():
        if getattr(args, name) != default:
            print(f"  [WARN] --{name.replace('_', '-')} no aplica al modo "
                  f"{args.mode}; ignorado.")


def main():
    args = build_parser().parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else None

    warn_inert_flags(args)

    if args.mode == "color":
        try:
            import vtracer  # noqa: F401 — fail fast antes de procesar
        except ImportError:
            print("El modo color requiere vtracer. Instala con: pip install vtracer")
            sys.exit(1)

        def run_one(f, out):
            return vectorize_color(
                f, output_path=out, preset=args.preset, max_dim=args.max_dim,
                filter_speckle=args.speckle, color_precision=args.colors,
                layer_difference=args.layer_diff, corner_threshold=args.corner,
                path_precision=args.path_precision,
            )
    else:
        common = dict(
            mode=args.mode, blur=args.blur,
            rdp_epsilon=args.rdp, chaikin=args.chaikin, tension=args.tension,
            stroke_width=args.width, auto_color=not args.no_auto_color,
            fallback_color=args.color or "#1a1a1a",
        )

        def run_one(f, out):
            return vectorize(f, output_path=out, **common)

    if input_path.is_dir():
        exts = (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp")
        files = sorted([f for f in input_path.iterdir() if f.suffix.lower() in exts])
        if not files:
            print(f"No se encontraron imágenes en {input_path}")
            return
        out_dir = output_path or input_path / "svg_output"
        out_dir.mkdir(exist_ok=True)
        print(f"Procesando {len(files)} imágenes ({args.mode})...\n")
        done, failed = 0, 0
        for i, f in enumerate(files, 1):
            print(f"[{i}/{len(files)}] {f.name}")
            try:
                run_one(f, out_dir / f.with_suffix(".svg").name)
                done += 1
            except Exception as e:
                print(f"   [ERR] {e}")
                failed += 1
            print()
        # Resumen agregado: comportamiento NUEVO de Fase 1 (declarado en spec)
        print(f"Resumen: {done} OK ({args.mode}), {failed} fallos.")
    else:
        run_one(input_path, output_path)
```

Nota: la lógica del modo directorio conserva el try/except por archivo existente; lo nuevo es el dispatch `run_one` y el resumen final.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_vectorize.py -v`
Expected: all PASS (los 5 nuevos y los anteriores)

- [ ] **Step 5: Manual CLI smoke**

```powershell
python vectorize.py --help
```

Expected: ayuda con `--mode {contour,skeleton,both,color}` y los flags nuevos, sin traceback.

- [ ] **Step 6: Commit**

```bash
git add tests/test_vectorize.py vectorize.py
git commit -m "feat: CLI color mode with inert-flag warnings, default stays contour"
```

---

### Task 6: Modo directorio — batch continúa ante archivos corruptos

Verifica el comportamiento integrado (spec, tabla de errores + grupo "Errores" del testing): un archivo corrupto no detiene el batch y el resumen lo cuenta.

**Files:**
- Test: `tests/test_vectorize.py` (solo test — la implementación quedó en Task 5)

- [ ] **Step 1: Write the test**

Append to `tests/test_vectorize.py`:

```python
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
```

- [ ] **Step 2: Run the test**

Run: `python -m pytest tests/test_vectorize.py::test_batch_continues_after_corrupt_file -v`
Expected: PASS (la implementación de Task 5 ya lo cubre; si falla, el bug está en el try/except o el resumen de `main()`)

- [ ] **Step 3: Run the full suite**

Run: `python -m pytest tests/test_vectorize.py -v`
Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_vectorize.py
git commit -m "test: batch directory mode survives corrupt files and reports summary"
```

---

### Task 7: requirements.txt y README

**Files:**
- Modify: `requirements.txt`
- Modify: `README.md`

- [ ] **Step 1: Update `requirements.txt`**

Replace the full content with:

```
opencv-contrib-python>=4.8
numpy>=1.24
# vtracer: wheels verificados solo en Windows / Python 3.14 (2026-06-05).
# En otras plataformas pip puede intentar compilar desde fuente (Rust).
vtracer>=0.6.15
# dev
pytest>=8
```

- [ ] **Step 2: Update `README.md`**

2a. Replace the intro paragraph (lines 1-5) with:

```markdown
# vectorizer

Convierte imágenes en SVG. Dos pipelines:

- **Handwriting** (PNG/JPG escaneadas): curvas Bézier suaves, color real del trazo, limpieza de ruido y líneas de cuaderno, contornos rellenos o centerline fino.
- **Color** (`--mode color`): logos, ilustraciones y fotos (posterizadas) vía [vtracer](https://github.com/visioncortex/vtracer), con presets y flags de ajuste fino.

Extraído de [sdar.dev](https://github.com/sssamuelll/sdar.dev), donde genera los specimens de handwriting del sitio.
```

2b. In the "Modos" table (after the `both` row), add:

```markdown
| `color` | vectorización full-color con vtracer — logos, ilustraciones, fotos. Opt-in explícito; el default sigue siendo `contour` |
```

2c. After the "Modos" section, add a new section:

```markdown
## Modo color

```bash
# logo / ilustración / foto → SVG full-color
python vectorize.py logo.png --mode color

# preset explícito (sin --preset se elige solo: ≤12 colores → logo, >12 → photo)
python vectorize.py dibujo.png --mode color --preset drawing
```

| flag | mapea a (vtracer) | preset logo | drawing | photo |
|---|---|---|---|---|
| `--colors` | `color_precision` | 6 | 7 | 8 |
| `--speckle` | `filter_speckle` | 8 | 4 | 4 |
| `--layer-diff` | `layer_difference` | 48 | 24 | 12 |
| `--corner` | `corner_threshold` | 45 | 60 | 60 |
| `--path-precision` | decimales de coordenadas | 3 | 3 | 3 |
| `--max-dim` | resize previo (0 = sin resize) | 1200 | 1200 | 1200 |

Notas:

- **`--preset drawing` solo se activa manualmente** — la selección automática elige entre `logo` y `photo`.
- **Las fotos generan SVGs pesados** (miles de paths). `--max-dim` es la mitigación; bajar `--colors` también ayuda.
- **Contrato de salida:** los SVGs del modo color son capas apiladas con fill por path — **no** llevan las clases `.ink`/`.stroke` de los modos handwriting. Si algo downstream depende de esas clases, solo debe consumir salidas de `contour`/`skeleton`/`both`.
- **Cambio de alpha (todos los modos):** los PNG con transparencia ahora se componen sobre blanco (antes el canal alpha se descartaba, dejando fondo negro). Para imágenes sin alpha nada cambia.
- Los flags handwriting (`--blur`, `--rdp`, etc.) no aplican al modo color; si los pasas, el script lo avisa con un warning.
```

2d. In the "Parámetros" table, update the `--mode` row:

```markdown
| `--mode` | `contour` | `contour` \| `skeleton` \| `both` \| `color` |
```

- [ ] **Step 3: Verify docs render and tests still pass**

Run: `python -m pytest tests/test_vectorize.py -q`
Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add requirements.txt README.md
git commit -m "docs: document color mode, presets, output contract, alpha change"
```

---

### Task 8: Verificación final

**Files:** ninguno nuevo — verificación integral.

- [ ] **Step 1: Full test suite**

Run: `python -m pytest tests/test_vectorize.py -v`
Expected: todos PASS (≈17 tests)

- [ ] **Step 2: Smoke real de ambos pipelines**

```powershell
python -c "
import numpy as np, cv2, tempfile, os
import vectorize as vz
d = tempfile.mkdtemp()
# handwriting sintético → pipeline clásico (default intacto)
hw = np.full((300, 300, 3), 255, np.uint8)
cv2.ellipse(hw, (150, 150), (80, 40), 30, 0, 360, (40, 40, 40), 3)
cv2.imwrite(os.path.join(d, 'trazo.png'), hw)
vz.vectorize(os.path.join(d, 'trazo.png'))
# logo sintético → pipeline color
logo = np.full((400, 400, 3), 255, np.uint8)
cv2.rectangle(logo, (40, 40), (200, 200), (60, 60, 230), -1)
cv2.circle(logo, (280, 280), 90, (230, 120, 40), -1)
cv2.imwrite(os.path.join(d, 'logo.png'), logo)
vz.vectorize_color(os.path.join(d, 'logo.png'))
print('AMBOS PIPELINES OK —', d)
"
```

Expected: dos `[OK] SVG:` y `AMBOS PIPELINES OK`. Abrir los SVGs en el navegador para inspección visual si se quiere.

- [ ] **Step 3: Smoke con una imagen real del usuario (si hay alguna a mano)**

```powershell
# con cualquier logo real que Samuel tenga:
python vectorize.py <ruta-al-logo-real.png> --mode color
```

Expected: SVG generado; inspección visual del resultado. Este paso alimenta el corpus de calibración de Fase 2.

- [ ] **Step 4: Final commit (si quedó algo suelto) y resumen**

```bash
git status
git log --oneline -10
```

Expected: working tree limpio, ~7 commits de Fase 1 sobre `main`.
