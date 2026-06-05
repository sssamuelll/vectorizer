# Fase A: Producto de Reporte de Aproximación de Fuentes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convertir el spike A.0 (gate APROBADO 2026-06-05) en el producto de reporte: OCR automático con negociación de idioma, clasificación escalar honesta, pool de 60 desde metadata real, probing de pesos `wght` 300–700, nominación API opt-in, reporte de dos niveles, `--json` (emisión draft) y `--preview`.

**Architecture:** Todo en `fontid.py` (crece de ~330 a ~700 líneas; `vectorize.py` NO se toca). El spike queda como núcleo intacto (segmentación+fusión, matching de factor común, descarga atómica); Fase A añade capas encima: metadata/pool, pesos, OCR/regiones, clasificación, API, reporte v2. El flujo manual (`--region`/`--text`) funciona en cualquier SO; el automático (OCR) es Windows-only con guard claro.

**Tech Stack:** Python 3.14, OpenCV, numpy, Pillow, urllib; `winocr` (OCR nativo Windows — YA instalado en esta máquina por la verificación de Halberg); `anthropic` (SOLO para `--api`, opt-in); pytest con marker `network`.

**Spec:** `docs/superpowers/specs/2026-06-05-font-identification-design.md` (v2), secciones "Fase A" completas + "Hechos runtime verificados".

**Hechos runtime que gobiernan este plan:**
1. Packs OCR de esta máquina: solo `es-ES`/`es-MX` — JAMÁS hardcodear `'en'`; negociar vía `available_recognizer_languages`.
2. El OCR NO emite región para texto caligráfico ("libre" desaparece) — aviso fijo en el reporte.
3. UA default de urllib → TTF directo. **NUEVO (verificado 2026-06-05): CSS2 con `family=X:wght@300..700` devuelve TTFs ESTÁTICOS separados, uno por peso, con descriptores `font-weight: NNN;` parseables.** El probing de pesos = descargar estáticos por peso.
4. Metadata GF: 1934 familias, JSON limpio, categorías Title Case (`"Serif"`, `"Sans Serif"`, `"Display"`).
5. winocr usa `asyncio.run` interno → OCR secuencial en hilo principal; las DESCARGAS sí se paralelizan (8 hilos).
6. Umbral de empate 0.03; margen serif-vs-sans ~0.2.
7. Evidencia del gate: el render top-1 se ve más pesado que el original — **el probing de pesos es la prioridad #1 informada por el gate** (se espera que promueva Cormorant Garamond Light en "mente").
8. API: spec eligió `claude-haiku-4-5` explícitamente (costo céntimos); structured outputs soportado en Haiku 4.5 vía `output_config={"format": {"type": "json_schema", ...}}`; `anthropic.Anthropic()` resuelve la key del entorno. La key sola NO activa nada — `--api` requerido.

---

## File Structure

| archivo | responsabilidad |
|---|---|
| `fontid.py` (modificar) | Núcleo del spike intacto + secciones nuevas: 1b fusión vertical, 3b metadata/pool, 3c pesos, 3d OCR/regiones, 3e clasificación, 3f API, 4b reporte v2/JSON/preview, CLI v2. |
| `tests/test_fontid.py` (modificar) | Tests del spike intactos + grupos Fase A. |
| `pytest.ini` (crear) | Marker `network` registrado, skip por default. |
| `requirements.txt` (modificar) | `+winocr` (Windows-only, comentado), `+anthropic` (opcional `--api`, comentado). |
| `README.md` (modificar) | Sección fontid. |
| `docs/calibration/2026-06-05-logo-libre-mente.md` (modificar, Task 9) | Resultado de la corrida de aceptación. |

---

### Task 1: Fusión vertical de componentes (segmentación Fase A)

Hecho runtime 5 del spec: sin fusión, "integrative" (11 letras) → 13 componentes (las íes parten). La fusión une componentes que se solapan en x (punto de la i, acentos).

**Files:**
- Modify: `fontid.py` (sección 1, después de `segment_glyphs`)
- Test: `tests/test_fontid.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_fontid.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_fontid.py -v -k fusion`
Expected: 2 FAIL with `AttributeError: ... 'segment_glyphs_fused'`

- [ ] **Step 3: Implement**

Insert in `fontid.py` right after `segment_glyphs`:

```python
def _x_overlap(a, b):
    """Fracción de solape horizontal entre dos intervalos (x0, x1)."""
    lo, hi = max(a[0], b[0]), min(a[1], b[1])
    if hi <= lo:
        return 0.0
    return (hi - lo) / min(a[1] - a[0], b[1] - b[0])


def segment_glyphs_fused(crop_bgr, min_area=4, overlap_frac=0.5):
    """Segmentación Fase A: componentes conexos + fusión vertical.

    Componentes cuyo rango x se solapa ≥ overlap_frac con otro (punto de
    la i/j, acentos) se fusionan en un solo glifo (spec, hecho runtime 5:
    sin esto 'integrative' da 13 componentes para 11 letras).
    """
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    flag = cv2.THRESH_BINARY_INV if np.mean(gray) > 127 else cv2.THRESH_BINARY
    _, binary = cv2.threshold(gray, 0, 255, flag | cv2.THRESH_OTSU)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(
        (binary > 0).astype(np.uint8), connectivity=8)
    boxes = []  # (x0, x1, y0, y1, comp_ids)
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < min_area:
            continue
        boxes.append([x, x + w, y, y + h, [i]])
    boxes.sort(key=lambda b: b[0])

    fused = []
    for b in boxes:
        if fused and _x_overlap((fused[-1][0], fused[-1][1]), (b[0], b[1])) >= overlap_frac:
            prev = fused[-1]
            prev[0] = min(prev[0], b[0]); prev[1] = max(prev[1], b[1])
            prev[2] = min(prev[2], b[2]); prev[3] = max(prev[3], b[3])
            prev[4].extend(b[4])
        else:
            fused.append(b)

    glyphs = []
    for x0, x1, y0, y1, ids in fused:
        m = np.isin(labels[y0:y1, x0:x1], ids)
        glyphs.append(m)
    return glyphs
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_fontid.py -v`
Expected: 12 PASS (10 del spike + 2 nuevos)

- [ ] **Step 5: Commit**

```bash
git add fontid.py tests/test_fontid.py
git commit -m "feat(fontid): vertical component fusion for dotted glyphs"
```

---

### Task 2: Caché formal + metadata de Google Fonts + pool

**Files:**
- Modify: `fontid.py` (nueva sección tras `download_ttf`)
- Create: `pytest.ini`
- Test: `tests/test_fontid.py`

- [ ] **Step 1: Create `pytest.ini`**

```ini
[pytest]
markers =
    network: requiere red real contra Google Fonts (skip por default)
addopts = -m "not network"
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_fontid.py`:

```python
# ═══════════════════════════════════════════════════════════════════
# FASE A — METADATA Y POOL (spec: hecho runtime 4, Title Case)
# ═══════════════════════════════════════════════════════════════════

import json
import pytest


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
    """--category 'serif' (minúscula del usuario) matchea 'Serif' (Title Case real)."""
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_fontid.py -v -k "pool_from or category_filter or size_caps"`
Expected: 3 FAIL with `AttributeError` (`fetch_metadata`/`build_pool` no existen)

- [ ] **Step 4: Implement**

Append to `fontid.py` after `download_ttf`:

```python
# ═══════════════════════════════════════════════════════════════════
# 3b. METADATA DE GOOGLE FONTS Y POOL (Fase A)
# ═══════════════════════════════════════════════════════════════════

import json
import time

CACHE_DIR_DEFAULT = str(Path.home() / ".cache" / "vectorizer-fonts")
GF_METADATA_URL = "https://fonts.google.com/metadata/fonts"
METADATA_TTL_S = 7 * 24 * 3600          # TTL semanal (spec, Caché)
# Categorías Title Case REALES del metadata (hecho runtime 4). El input
# del usuario se normaliza antes de comparar.
POOL_CATEGORIES = ("Serif", "Sans Serif", "Display")


def _normalize_category(cat):
    """'sans-serif' / 'SERIF' / 'sans serif' → forma Title Case real."""
    return cat.replace("-", " ").strip().title()


def fetch_metadata(cache_dir):
    """Metadata de GF con caché TTL semanal. Devuelve familyMetadataList.

    Sin red y sin caché → RuntimeError con mensaje claro. Sin red CON
    caché vencida → usa la caché vencida con warning (mejor que nada).
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = cache_dir / "metadata.json"
    fresh = dest.exists() and (time.time() - dest.stat().st_mtime) < METADATA_TTL_S
    if not fresh:
        try:
            raw = urllib.request.urlopen(GF_METADATA_URL, timeout=30).read()
            tmp = dest.with_suffix(".json.tmp")
            tmp.write_bytes(raw)
            json.loads(raw.decode("utf-8"))     # valida antes de promover
            os.replace(tmp, dest)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            if not dest.exists():
                raise RuntimeError(
                    "No se pudo descargar la metadata de Google Fonts y no hay "
                    "caché previa. Revisa la red o usa --region/--text con "
                    "--pool-file manual.") from None
            print("  [WARN] metadata GF: sin red; usando caché vencida.")
    return json.loads(dest.read_text(encoding="utf-8"))["familyMetadataList"]


def build_pool(metadata, pool_size=60, category=None):
    """Pool por popularidad. Default: Serif + Sans Serif + Display.

    `category` (input de usuario, cualquier casing) se normaliza a la
    forma Title Case real del metadata.
    """
    cats = (POOL_CATEGORIES if category is None
            else (_normalize_category(category),))
    fams = [m for m in metadata if m.get("category") in cats]
    fams.sort(key=lambda m: m.get("popularity", 10 ** 9))
    return [m["family"] for m in fams[:pool_size]]
```

Mueve los `import json` / `import time` al bloque de imports del tope del archivo (no los dejes mid-file; el banner de sección se queda donde está).

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_fontid.py -v`
Expected: 15 PASS (los network siguen skip)

Run network una vez manualmente: `python -m pytest tests/test_fontid.py -v -m network -k metadata`
Expected: 1 PASS

- [ ] **Step 6: Commit**

```bash
git add fontid.py tests/test_fontid.py pytest.ini
git commit -m "feat(fontid): GF metadata cache with weekly TTL and popularity pool"
```

---

### Task 3: Probing de pesos wght 300–700

Prioridad #1 informada por el gate (los renders top-1 salieron más pesados que el original). Hecho runtime verificado: CSS2 con `wght@300..700` devuelve TTFs estáticos por peso con descriptores `font-weight: NNN;`.

**Files:**
- Modify: `fontid.py` (sección 3c, tras build_pool)
- Test: `tests/test_fontid.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_fontid.py`:

```python
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
    """Cormorant Garamond real: descarga ≥3 pesos; el matching elige uno."""
    weights = fi.download_family_weights("Cormorant Garamond", tmp_path)
    assert len(weights) >= 3
    assert all(p.exists() for _, p in weights)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_fontid.py -v -k "weight or match_family"`
Expected: 2 FAIL with `AttributeError`

- [ ] **Step 3: Implement**

Append to `fontid.py` (sección 3c):

```python
# ═══════════════════════════════════════════════════════════════════
# 3c. PROBING DE PESOS (Fase A — prioridad #1 del gate A.0)
# ═══════════════════════════════════════════════════════════════════

WGHT_RANGE = "300..700"


def parse_weight_css(css):
    """CSS2 → [(wght, url_ttf)] por bloque @font-face (hecho runtime nuevo:
    GF entrega estáticos por peso con descriptores font-weight)."""
    pairs = []
    for block in css.split("@font-face")[1:]:
        mw = re.search(r"font-weight:\s*(\d+)", block)
        mu = re.search(r"url\((https://[^)]+\.ttf)\)", block)
        if mw and mu:
            pairs.append((int(mw.group(1)), mu.group(1)))
    return pairs


def download_family_weights(family, cache_dir):
    """Descarga los pesos estáticos 300..700 de una familia (atómico+validado).

    Devuelve [(wght, Path)] de los que existen/validaron. Lista vacía si la
    red falla por completo (el caller cuenta la familia como omitida).
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    base = family.replace(" ", "_")
    try:
        url = GF_CSS2.format(urllib.parse.quote_plus(family)) + ":wght@" + WGHT_RANGE
        css = urllib.request.urlopen(url, timeout=20).read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError):
        return []
    out = []
    for wght, ttf_url in parse_weight_css(css):
        dest = cache_dir / f"{base}_{wght}.ttf"
        if not dest.exists():
            try:
                data = urllib.request.urlopen(ttf_url, timeout=30).read()
            except (urllib.error.URLError, TimeoutError, OSError):
                continue
            tmp = dest.with_suffix(".tmp")
            tmp.write_bytes(data)
            if not validate_ttf(tmp):
                tmp.unlink(missing_ok=True)
                continue
            os.replace(tmp, dest)
        out.append((wght, dest))
    return out


def match_candidate_detail(crop_glyphs, chars, ttf_path, base_size=96):
    """Como match_candidate pero devuelve (score, factor_de_escala) — el
    factor lo necesita el JSON de Fase A (requisito de información de
    Fase B registrado en el spec)."""
    if len(crop_glyphs) < 2 or len(crop_glyphs) != len(chars):
        return None
    font = ImageFont.truetype(str(ttf_path), base_size)
    rendered = [render_glyph(c, font) for c in chars]
    if any(r is None for r in rendered):
        return None
    crop_med = float(np.median([g.shape[0] for g in crop_glyphs]))
    rend_med = float(np.median([r.shape[0] for r in rendered]))
    if rend_med <= 0 or crop_med <= 0:
        return None
    s = crop_med / rend_med
    ious = []
    for g, r in zip(crop_glyphs, rendered):
        rs = cv2.resize(
            r.astype(np.uint8),
            (max(1, int(round(r.shape[1] * s))), max(1, int(round(r.shape[0] * s)))),
            interpolation=cv2.INTER_AREA) > 0
        if not rs.any():
            return None
        ious.append(_iou_centroid(g, rs))
    ious.sort()
    if len(ious) >= 4:
        ious = ious[1:]
    return float(np.mean(ious)), s


def match_family_local(crop_glyphs, chars, weight_paths):
    """Prueba cada (wght, ttf) y conserva el mejor. → (score, wght, s) | None."""
    best = None
    for wght, path in weight_paths:
        r = match_candidate_detail(crop_glyphs, chars, path)
        if r is None:
            continue
        score, s = r
        if best is None or score > best[0]:
            best = (score, wght, s)
    return best
```

Refactor sin romper el spike: reescribe el cuerpo de `match_candidate` para delegar:

```python
def match_candidate(crop_glyphs, chars, ttf_path, base_size=96):
    """Wrapper de compatibilidad del spike: solo el score."""
    r = match_candidate_detail(crop_glyphs, chars, ttf_path, base_size)
    return None if r is None else r[0]
```

(Borra el cuerpo duplicado anterior de `match_candidate` — la lógica vive ahora en `match_candidate_detail`. Los docstrings del contrato — media truncada, <2 glifos — se mueven con ella.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_fontid.py -v`
Expected: 17 PASS (el spike completo sigue verde — el refactor de match_candidate es transparente)

Run network: `python -m pytest tests/test_fontid.py -v -m network -k weight`
Expected: 1 PASS

- [ ] **Step 5: Commit**

```bash
git add fontid.py tests/test_fontid.py
git commit -m "feat(fontid): static-weight probing 300-700 with recorded wght and scale"
```

---

### Task 4: OCR con negociación de idioma + detección de regiones

**Files:**
- Modify: `fontid.py` (sección 3d)
- Test: `tests/test_fontid.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_fontid.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_fontid.py -v -k "negotiate or detect_regions"`
Expected: 2 FAIL with `AttributeError`

- [ ] **Step 3: Implement**

Append to `fontid.py` (sección 3d):

```python
# ═══════════════════════════════════════════════════════════════════
# 3d. OCR Y REGIONES (Fase A — Windows-only; el flujo manual
#     --region/--text funciona en cualquier SO)
# ═══════════════════════════════════════════════════════════════════

LATIN_PREFIXES = ("en", "es", "fr", "de", "it", "pt", "nl", "ca")
OCR_INSTALL_HINT = (
    "No hay ningún language pack OCR de script latino instalado.\n"
    "Instala uno (PowerShell como admin):\n"
    '  Add-WindowsCapability -Online -Name "Language.OCR~~~es-ES~0.0.1.0"')


def negotiate_ocr_language():
    """Primer recognizer de script latino DISPONIBLE — jamás hardcodear
    'en' (hecho runtime 1: esta máquina solo tiene es-ES/es-MX y lang='en'
    lanza AssertionError)."""
    from winsdk.windows.media.ocr import OcrEngine  # import lazy
    # winsdk expone la propiedad estática como método get_* o como property
    # según versión — tolera ambas formas:
    getter = getattr(OcrEngine, "get_available_recognizer_languages", None)
    langs = getter() if callable(getter) else OcrEngine.available_recognizer_languages
    tags = [l.language_tag for l in langs]
    for tag in tags:
        if tag.split("-")[0].lower() in LATIN_PREFIXES:
            return tag
    raise RuntimeError(OCR_INSTALL_HINT + f"\nDisponibles: {tags or 'ninguno'}")


def detect_regions(img_bgr):
    """OCR → una región por LÍNEA detectada (criterio de agrupación
    declarado: líneas distintas suelen ser fuentes distintas en un logo).

    Devuelve [{'bbox': (x0,y0,x1,y1) ABSOLUTAS, 'text': str,
               'word_boxes': [(x0,y0,x1,y1), ...]}].
    Limitación documentada (hecho runtime 2): el OCR puede NO emitir
    región para texto caligráfico — el caller imprime el aviso fijo.
    """
    if sys.platform != "win32":
        raise RuntimeError(
            "La detección automática usa el OCR nativo de Windows (winocr) "
            "y es Windows-only. Usa --region/--text en este SO.")
    try:
        import winocr
    except ImportError:
        raise RuntimeError(
            "El flujo automático requiere winocr. Instala con: "
            "pip install winocr  (o usa --region/--text)") from None
    lang = negotiate_ocr_language()
    try:
        result = winocr.recognize_cv2_sync(img_bgr, lang)
    except Exception as e:
        raise RuntimeError(
            f"El OCR falló en runtime ({e}). Fallback: pasa las regiones a "
            "mano con --region/--text.") from None

    regions = []
    for line in result.get("lines", []) if isinstance(result, dict) else result.lines:
        words = line["words"] if isinstance(line, dict) else line.words
        boxes = []
        for w in words:
            r = w["bounding_rect"] if isinstance(w, dict) else w.bounding_rect
            x = int(r["x"] if isinstance(r, dict) else r.x)
            y = int(r["y"] if isinstance(r, dict) else r.y)
            ww = int(r["width"] if isinstance(r, dict) else r.width)
            hh = int(r["height"] if isinstance(r, dict) else r.height)
            boxes.append((x, y, x + ww, y + hh))
        if not boxes:
            continue
        text = line["text"] if isinstance(line, dict) else line.text
        x0 = min(b[0] for b in boxes); y0 = min(b[1] for b in boxes)
        x1 = max(b[2] for b in boxes); y1 = max(b[3] for b in boxes)
        regions.append({"bbox": (x0, y0, x1, y1), "text": text,
                        "word_boxes": boxes})
    return regions
```

Nota para el implementador: winocr puede devolver objetos winrt o dicts según versión — el código de arriba tolera ambos. Si `recognize_cv2_sync` no existe en la versión instalada, usa `recognize_pil_sync(Image.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)), lang)` — verifica con `dir(winocr)` y ajusta, reportándolo.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_fontid.py -v`
Expected: 19 PASS

- [ ] **Step 5: Commit**

```bash
git add fontid.py tests/test_fontid.py
git commit -m "feat(fontid): Windows OCR with language negotiation and per-line regions"
```

---

### Task 5: Clasificación escalar (reframed por Voronov)

NO es tricotomía ontológica: es un score escalar con dos cortes (banda de incertidumbre declarada) y estadísticas crudas siempre visibles.

**Files:**
- Modify: `fontid.py` (sección 3e)
- Test: `tests/test_fontid.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_fontid.py`:

```python
# ═══════════════════════════════════════════════════════════════════
# FASE A — CLASIFICACIÓN ESCALAR (spec: score + banda + stats crudas)
# ═══════════════════════════════════════════════════════════════════

def test_classify_typeset_line_scores_type():
    """Línea renderizada con fuente → lado tipografía, con stats crudas."""
    crop = _render_word_bgr("mente sana", WIN_FONTS / "georgia.ttf")
    glyphs = fi.segment_glyphs_fused(crop)
    c = fi.classify_region(glyphs, "mente sana")
    assert c["label"] == "type"
    assert "baseline_residual" in c and "height_var" in c
    assert 0.0 <= c["score"] <= 1.0


def test_classify_jittered_glyphs_scores_handwriting_side():
    """Glifos con jitter vertical y de escala (simula mano) → score más bajo
    que la versión tipográfica de la misma palabra."""
    crop = _render_word_bgr("mente sana", WIN_FONTS / "georgia.ttf")
    clean = fi.classify_region(fi.segment_glyphs_fused(crop), "mente sana")
    rng = np.random.default_rng(11)
    jittered = []
    for g in fi.segment_glyphs_fused(crop):
        scale = rng.uniform(0.7, 1.4)
        h = max(2, int(g.shape[0] * scale)); w = max(2, int(g.shape[1] * scale))
        m = cv2.resize(g.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST) > 0
        pad_top = int(rng.uniform(0, 18))
        m = np.vstack([np.zeros((pad_top, m.shape[1]), bool), m])
        jittered.append(m)
    jit = fi.classify_region(jittered, "mente sana")
    assert jit["score"] < clean["score"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_fontid.py -v -k classify`
Expected: 2 FAIL with `AttributeError`

- [ ] **Step 3: Implement**

Append to `fontid.py` (sección 3e):

```python
# ═══════════════════════════════════════════════════════════════════
# 3e. CLASIFICACIÓN ESCALAR (Fase A — reframe del spec: un score con
#     dos cortes; 'uncertain' es estado del clasificador, no del mundo)
# ═══════════════════════════════════════════════════════════════════

# Constantes PROVISIONALES (sin corpus de calibración aún — el spec lo
# declara). Las stats crudas se reportan siempre; los cortes solo etiquetan.
CLASSIFY_TYPE_CUT = 0.65        # score ≥ → "type"
CLASSIFY_HAND_CUT = 0.45        # score ≤ → "handwriting"; entre ambos → "uncertain"
_RESIDUAL_NORM_PX = 4.0         # residuo de baseline que ya cuenta como irregular
_HEIGHT_VAR_NORM = 0.35         # variación relativa de altura idem


def classify_region(glyph_masks, text):
    """Score escalar tipografía↔handwriting con estadísticas crudas.

    Señales: (1) residuo de baseline (fit lineal de los bottoms de los
    glifos), (2) variación relativa de altura, (3) repetición de formas
    SOLO si el texto tiene letras repetidas (declarado en el resultado).
    """
    if len(glyph_masks) < 2:
        return {"label": "uncertain", "score": 0.5, "baseline_residual": 0.0,
                "height_var": 0.0, "repeats_used": False,
                "note": "región con <2 glifos — señales insuficientes"}

    bottoms, heights, xs = [], [], []
    x_cursor = 0
    for m in glyph_masks:
        ys, _ = np.where(m)
        bottoms.append(float(ys.max()))
        heights.append(float(m.shape[0]))
        xs.append(float(x_cursor)); x_cursor += m.shape[1]
    bottoms, heights, xs = map(np.array, (bottoms, heights, xs))

    coef = np.polyfit(xs, bottoms, 1)
    residual = float(np.std(bottoms - np.polyval(coef, xs)))
    height_var = float(np.std(heights) / max(np.mean(heights), 1e-6))

    s_base = max(0.0, 1.0 - residual / _RESIDUAL_NORM_PX)
    s_height = max(0.0, 1.0 - height_var / _HEIGHT_VAR_NORM)
    parts = [s_base, s_height]

    chars = [c for c in text.lower() if not c.isspace()]
    repeats_used = False
    if len(chars) == len(glyph_masks):
        from collections import defaultdict
        idx = defaultdict(list)
        for i, c in enumerate(chars):
            idx[c].append(i)
        rep_ious = []
        for positions in idx.values():
            for a, b in zip(positions, positions[1:]):
                ga, gb = glyph_masks[a], glyph_masks[b]
                gb_r = cv2.resize(gb.astype(np.uint8),
                                  (max(1, ga.shape[1]), max(1, ga.shape[0])),
                                  interpolation=cv2.INTER_AREA) > 0
                rep_ious.append(_iou_centroid(ga, gb_r))
        if rep_ious:
            repeats_used = True
            parts.append(float(np.mean(rep_ious)))

    score = float(np.mean(parts))
    label = ("type" if score >= CLASSIFY_TYPE_CUT
             else "handwriting" if score <= CLASSIFY_HAND_CUT
             else "uncertain")
    return {"label": label, "score": round(score, 3),
            "baseline_residual": round(residual, 2),
            "height_var": round(height_var, 3), "repeats_used": repeats_used}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_fontid.py -v`
Expected: 21 PASS

- [ ] **Step 5: Commit**

```bash
git add fontid.py tests/test_fontid.py
git commit -m "feat(fontid): scalar type/handwriting classifier with raw stats"
```

---

### Task 6: Nominación API opt-in (claude-haiku-4-5, structured output)

La API NUNCA se activa por la sola presencia de la key (privacidad de logos de clientes — hallazgo Serrano); `--api` requerido. Solo nomina; la verificación es local. Máximo 1 call por invocación. Modelo: el spec eligió explícitamente `claude-haiku-4-5` (decisión registrada; costo céntimos).

**Files:**
- Modify: `fontid.py` (sección 3f)
- Test: `tests/test_fontid.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_fontid.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_fontid.py -v -k "api_nomination or merge_nominations"`
Expected: 2 FAIL with `AttributeError`

- [ ] **Step 3: Implement**

Append to `fontid.py` (sección 3f):

```python
# ═══════════════════════════════════════════════════════════════════
# 3f. NOMINACIÓN API (Fase A — opt-in explícito con --api; la sola
#     presencia de ANTHROPIC_API_KEY no activa nada. La API solo NOMINA:
#     toda verificación es local. Hallazgo Null Vale reconocido: nominar
#     dentro de un pool acotado ES decidir el espacio de búsqueda — por
#     eso el default es sin API y lo nominado se marca [API].)
# ═══════════════════════════════════════════════════════════════════

import base64

NOMINATION_MODEL = "claude-haiku-4-5"   # decisión del spec (costo céntimos)
NOMINATION_SCHEMA = {
    "type": "object",
    "properties": {
        "families": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["families"],
    "additionalProperties": False,
}


def nominate_via_api(crop_pngs, texts, max_families=10):
    """UN solo call de visión → hasta 10 nombres de familias GF plausibles.

    Cualquier fallo (SDK ausente, key ausente, error de API) → lista
    vacía con warning. El pipeline local sigue idéntico.
    """
    try:
        import anthropic
    except ImportError:
        print("  [WARN] --api: el paquete 'anthropic' no está instalado "
              "(pip install anthropic). Sigo sin nominación.")
        return []
    content = []
    for png in crop_pngs:
        content.append({"type": "image",
                        "source": {"type": "base64", "media_type": "image/png",
                                   "data": base64.standard_b64encode(png).decode()}})
    content.append({"type": "text", "text": (
        "Cada imagen es un recorte de texto tipográfico de un logo. Los "
        f"textos son: {texts}. Nombra hasta {max_families} familias de "
        "GOOGLE FONTS (nombres exactos del catálogo) visualmente más "
        "parecidas a la tipografía de los recortes, ordenadas de más a "
        "menos plausible.")})
    try:
        client = anthropic.Anthropic()   # resuelve ANTHROPIC_API_KEY del entorno
        resp = client.messages.create(
            model=NOMINATION_MODEL,
            max_tokens=1024,
            output_config={"format": {"type": "json_schema",
                                      "schema": NOMINATION_SCHEMA}},
            messages=[{"role": "user", "content": content}],
        )
        text = next(b.text for b in resp.content if b.type == "text")
        fams = json.loads(text)["families"][:max_families]
        return [f.strip() for f in fams if isinstance(f, str) and f.strip()]
    except Exception as e:
        print(f"  [WARN] --api falló ({type(e).__name__}); sigo sin nominación.")
        return []


def merge_nominations(pool, nominated):
    """Nominadas primero (prioridad), sin duplicados. Devuelve además el
    set de familias que entraron SOLO por la API (para marcar [API])."""
    api_only = {f for f in nominated if f not in pool}
    merged = list(dict.fromkeys(list(nominated) + list(pool)))
    return merged, api_only
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_fontid.py -v`
Expected: 23 PASS

- [ ] **Step 5: Commit**

```bash
git add fontid.py tests/test_fontid.py
git commit -m "feat(fontid): opt-in API nomination via claude-haiku-4-5 structured output"
```

---

### Task 7: Ranking v2, reporte de dos niveles, --json (emisión draft), --preview y CLI v2

El task de integración. Reescribe el flujo: regiones (auto u manuales) → clasificación → matching con pesos sobre el pool de metadata → reporte/JSON/preview.

**Files:**
- Modify: `fontid.py` (sección 4 reescrita: rank + reporte + CLI)
- Test: `tests/test_fontid.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_fontid.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_fontid.py -v -k "rank_region_v2 or json_draft or preview_strip or cli_v2"`
Expected: 4 FAIL with `AttributeError` (cli_manual puede pasar ya)

- [ ] **Step 3: Implement — ranking v2, JSON, preview**

Append to `fontid.py` (sección 4b, antes del CLI):

```python
# ═══════════════════════════════════════════════════════════════════
# 4b. RANKING V2, JSON DRAFT Y PREVIEW (Fase A)
# ═══════════════════════════════════════════════════════════════════

from concurrent.futures import ThreadPoolExecutor

DOWNLOAD_WORKERS = 8     # presupuesto del spec: descarga paralela; el OCR
                         # NUNCA se paraleliza (asyncio.run, hecho runtime 5)


def prepare_pool_weights(families, cache_dir):
    """Descarga (paralela, atómica) los pesos de cada familia.
    → dict familia → [(wght, Path)] (vacío = omitida por red)."""
    with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as ex:
        results = ex.map(lambda f: (f, download_family_weights(f, cache_dir)),
                         families)
    return dict(results)


def rank_families(crop_glyphs, chars, family_weights, api_set):
    """→ filas ordenadas desc: {family, overlap, wght, scale, api}."""
    rows = []
    for fam, weights in family_weights.items():
        if not weights:
            continue
        best = match_family_local(crop_glyphs, chars, weights)
        if best is None:
            continue
        score, wght, s = best
        rows.append({"family": fam, "overlap": round(score, 3), "wght": wght,
                     "scale": round(s, 4), "api": fam in api_set})
    rows.sort(key=lambda r: -r["overlap"])
    return rows


def build_json_draft(regions):
    """Emisión draft (spec Fase B condición 3: NO es contrato hasta que
    Fase B firme sus requisitos). Sin '%', bboxes absolutas, wght y scale
    registrados por candidata."""
    out_regions = []
    for reg in regions:
        rows = reg["rows"]
        ties = tie_flags([(r["family"], r["overlap"]) for r in rows])
        cands = []
        for i, (r, tie) in enumerate(zip(rows, ties)):
            delta = (round(rows[i - 1]["overlap"] - r["overlap"], 3)
                     if i > 0 else None)
            cands.append({**r, "delta_to_next": delta, "tie_with_leader": tie})
        out_regions.append({
            "bbox": list(reg["bbox"]), "text": reg["text"],
            "classification": reg["classification"],
            "candidates": cands, "skipped": reg.get("skipped", 0),
        })
    return {"draft": True,
            "note": ("Emisión draft — el esquema puede cambiar cuando Fase B "
                     "firme sus requisitos de información (ver spec)."),
            "corpus": "Google Fonts",
            "regions": out_regions}


def write_preview(crop_bgr, text, top_rows, out_path, cache_dir, ink=(135, 177, 164)):
    """Tira comparativa: crop original | top-N renders al peso elegido.

    Busca cada TTF como {cache_dir}/{Familia_con_guiones}_{wght}.ttf —
    el nombre exacto que escribe download_family_weights.
    """
    h = crop_bgr.shape[0]
    panels = [crop_bgr]
    for r in top_rows:
        ttf = Path(cache_dir) / f"{r['family'].replace(' ', '_')}_{r['wght']}.ttf"
        if not ttf.exists():
            continue
        font = ImageFont.truetype(str(ttf), max(24, int(h * 0.7)))
        bbox = font.getbbox(text)
        img = Image.new("RGB", (bbox[2] - bbox[0] + 24, bbox[3] - bbox[1] + 24),
                        (255, 255, 255))
        ImageDraw.Draw(img).text((12 - bbox[0], 12 - bbox[1]), text,
                                 fill=ink[::-1], font=font)
        panel = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        panel = cv2.resize(panel, (max(1, int(panel.shape[1] * h / panel.shape[0])), h))
        panels.append(np.full((h, 16, 3), 255, np.uint8))
        panels.append(panel)
    cv2.imwrite(str(out_path), cv2.hconcat(panels))
    return out_path
```

Nota: `write_preview` recibe rows ya rankeadas; en el flujo real el cache_dir activo se pasa — ajusta la firma a `write_preview(crop_bgr, text, top_rows, out_path, cache_dir, ink=...)` y busca primero en ese `cache_dir`. El test pasa `tmp_path/"fonts"`… ajusta el test helper para copiar a `Georgia_400.ttf` dentro del cache que pases. (El implementador alinea test+firma; el contrato es: encuentra el TTF del par familia/wght en el cache_dir dado.)

- [ ] **Step 4: Implement — reporte v2 y CLI v2 (reemplaza `print_region_report` y `main`)**

Reemplaza `print_region_report` por:

```python
def print_region_report(idx, reg):
    cls = reg["classification"]
    print(f"\n[REGIÓN {idx}] \"{reg['text']}\" — {cls['label']} "
          f"(score {cls['score']}, baseline res={cls['baseline_residual']}px, "
          f"var. altura={cls['height_var']}"
          f"{', repetición usada' if cls.get('repeats_used') else ''})")
    if cls["label"] == "handwriting":
        print("  → se vectoriza, no se aproxima (territorio de vectorize.py)")
        return
    if cls["label"] == "uncertain":
        print("  banda incierta — revisa el crop o fuerza con --region/--text")
    rows = reg["rows"]
    if not rows:
        print("  sin candidatas rankeables")
        return
    # Separación por cluster (spec, reporte de dos niveles): el pool mezcla
    # categorías GF, así que el mejor de OTRA categoría es la línea base —
    # no hacen falta controles artificiales como en el spike.
    leader_cat = rows[0].get("category")
    others = [r["overlap"] for r in rows if r.get("category") not in (leader_cat, None)]
    if leader_cat and others:
        sep = rows[0]["overlap"] - max(others)
        band = "OK" if sep > 0.2 else ("MARGINAL" if sep > 0.1 else "DÉBIL")
        print(f"  cluster: {leader_cat} — separación vs mejor de otra "
              f"categoría: {sep:.3f} ({band})")
    ties = tie_flags([(r["family"], r["overlap"]) for r in rows])
    prev = None
    for i, (r, tie) in enumerate(zip(rows[:5], ties[:5]), 1):
        delta = f"   Δ {prev - r['overlap']:.3f}" if prev is not None else ""
        mark = "  → EMPATE con el líder" if tie else ""
        api = "  [API]" if r["api"] else ""
        print(f"  {i}. {r['family']:<24s} overlap {r['overlap']:.3f} "
              f"(wght {r['wght']}){delta}{mark}{api}")
        prev = r["overlap"]
    if reg.get("skipped"):
        print(f"  ({reg['skipped']} candidatas omitidas por red/validación)")
```

Reemplaza `build_parser`, `validate_args` y `main` por:

```python
def build_parser():
    p = argparse.ArgumentParser(
        description="Fase A — aproximación de fuentes (Google Fonts). "
                    "NO identifica: aproxima.")
    p.add_argument("input", help="Imagen del logo")
    p.add_argument("--region", action="append",
                   help="x0,y0,x1,y1 (repetible, pareado con --text; "
                        "sin esto, OCR automático — Windows-only)")
    p.add_argument("--text", action="append",
                   help="Texto de la región (repetible, pareado con --region)")
    p.add_argument("--pool", type=int, default=60,
                   help="Tamaño del pool de candidatas (default 60)")
    p.add_argument("--category", default=None,
                   help="Limita el pool a una categoría GF (serif, sans-serif, display)")
    p.add_argument("--api", action="store_true",
                   help="Nominación vía API de Claude (OPT-IN: envía los crops "
                        "a Anthropic; la sola presencia de la key no activa nada)")
    p.add_argument("--json", action="store_true", help="Salida JSON (emisión draft)")
    p.add_argument("--preview", action="store_true",
                   help="Tira PNG comparativa por región (junto al input)")
    p.add_argument("--cache-dir", default=CACHE_DIR_DEFAULT,
                   help="Caché de TTFs y metadata")
    return p


def validate_args(args):
    if (args.region is None) != (args.text is None):
        sys.exit("error: --region y --text van juntos")
    if args.region and len(args.region) != len(args.text):
        sys.exit(f"error: --region ({len(args.region)}) y --text "
                 f"({len(args.text)}) deben ir pareados posicionalmente")


def _manual_regions(img, args):
    regions = []
    for reg, text in zip(args.region, args.text):
        try:
            x0, y0, x1, y1 = (int(v) for v in reg.split(","))
        except ValueError:
            sys.exit(f"error: región inválida {reg!r} (formato x0,y0,x1,y1)")
        crop = img[y0:y1, x0:x1]
        if crop.size == 0:
            sys.exit(f"error: región {reg!r} fuera de los límites de la imagen "
                     f"{img.shape[1]}x{img.shape[0]}")
        regions.append({"bbox": (x0, y0, x1, y1), "text": text})
    return regions


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # el reporte usa Δ/→/≠; cp1252 crashea
    args = build_parser().parse_args()
    validate_args(args)
    img = load_image_bgr(args.input)
    if img is None:
        raise ValueError(f"No se pudo cargar: {args.input}")

    if args.region:
        raw_regions = _manual_regions(img, args)
        forced = True
    else:
        try:
            raw_regions = detect_regions(img)
        except RuntimeError as e:
            sys.exit(f"error: {e}")
        forced = False
        if not raw_regions:
            sys.exit("sin regiones de texto detectadas — usa --region/--text")

    metadata = fetch_metadata(args.cache_dir)
    pool = build_pool(metadata, pool_size=args.pool, category=args.category)

    api_set = set()
    if args.api:
        crops_png = []
        for reg in raw_regions:
            x0, y0, x1, y1 = reg["bbox"]
            ok, buf = cv2.imencode(".png", img[y0:y1, x0:x1])
            if ok:
                crops_png.append(buf.tobytes())
        nominated = nominate_via_api(crops_png, [r["text"] for r in raw_regions])
        pool, api_set = merge_nominations(pool, nominated)

    family_weights = prepare_pool_weights(pool, args.cache_dir)
    skipped_total = sum(1 for w in family_weights.values() if not w)

    print(CORPUS_NOTE)
    results = []
    for i, reg in enumerate(raw_regions, 1):
        x0, y0, x1, y1 = reg["bbox"]
        glyphs = segment_glyphs_fused(img[y0:y1, x0:x1])
        chars = [c for c in reg["text"] if not c.isspace()]
        cls = (classify_region(glyphs, reg["text"]) if not forced
               else {"label": "type", "score": 1.0, "baseline_residual": 0.0,
                     "height_var": 0.0, "repeats_used": False,
                     "note": "región forzada por el usuario"})
        entry = {"bbox": reg["bbox"], "text": reg["text"],
                 "classification": cls, "rows": [], "skipped": skipped_total}
        if cls["label"] != "handwriting":
            if len(glyphs) != len(chars):
                print(f"\n[REGIÓN {i}] \"{reg['text']}\" — segmentación≠texto "
                      f"({len(glyphs)} glifos vs {len(chars)} chars) — no se rankea.")
                results.append(entry)
                continue
            entry["rows"] = rank_families(glyphs, chars, family_weights, api_set)
            cat_by_family = {m["family"]: m.get("category") for m in metadata}
            for r in entry["rows"]:
                r["category"] = cat_by_family.get(r["family"])
        print_region_report(i, entry)
        if args.preview and entry["rows"]:
            out = Path(args.input).with_name(
                Path(args.input).stem + f"_fontid_r{i}.png")
            write_preview(img[y0:y1, x0:x1], reg["text"], entry["rows"][:3],
                          out, args.cache_dir)
            print(f"  preview: {out}")
        results.append(entry)

    if not forced:
        print("\nAviso: zonas con texto caligráfico pueden no listarse arriba "
              "(el OCR no siempre emite región para handwriting). Usa "
              "--region/--text para forzarlas.")
    if args.json:
        print(json.dumps(build_json_draft(results), ensure_ascii=False, indent=2))
```

Notas para el implementador:
- Los tests del spike `test_cli_region_text_pairing` y `test_pool_has_controls` deben seguir verdes: `SPIKE_POOL`/`CONTROLES`/`TIE_DELTA`/`tie_flags` se conservan (los controles ya no corren en el flujo v2 — eran el instrumento del gate; las constantes quedan como registro y para los tests).
- `rank_region` (spike) puede quedar como está (sin usar por main) o borrarse junto con la adaptación de sus tests — decisión: **se conserva** para no tocar tests del spike. El reporte viejo es reemplazado; ajusta los tests del spike que referencien `print_region_report` solo si existen (no existen — verifica con grep).
- El campo `controls` de `print_region_report` es opcional (solo lo llena quien quiera medir separación; el flujo v2 normal no lo llena).

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest tests/test_fontid.py -v`
Expected: 28 PASS — incluye TODOS los del spike sin modificar

Run: `python -m pytest tests/ -q`
Expected: 45 passed (17 vectorize + 28 fontid)

- [ ] **Step 6: Commit**

```bash
git add fontid.py tests/test_fontid.py
git commit -m "feat(fontid): Fase A pipeline — auto regions, two-level report, json draft, preview"
```

---

### Task 8: requirements.txt y README

**Files:**
- Modify: `requirements.txt`, `README.md`

- [ ] **Step 1: Update `requirements.txt`** — añade al final:

```
# fontid (aproximación de fuentes):
# winocr usa el OCR nativo de Windows (winrt) — Windows-only; además
# requiere un language pack OCR de script latino instalado en el SO.
winocr
# anthropic: SOLO para fontid --api (nominación opt-in). Opcional.
anthropic
```

- [ ] **Step 2: Update `README.md`** — nueva sección después de "## Modo color":

````markdown
## fontid — aproximación de fuentes (Fase A)

Cuando un logo contiene texto compuesto en una fuente, recomponerlo desde el
archivo de fuente supera cualquier vectorización. `fontid.py` encuentra **la
alternativa más cercana dentro de Google Fonts** — no identifica la fuente
original (que probablemente es comercial); aproxima, y lo dice en cada reporte.

```bash
python fontid.py logo.png                          # automático (OCR — Windows-only)
python fontid.py logo.png --region 450,600,1050,770 --text "mente"   # manual (cualquier SO)
python fontid.py logo.png --preview --json         # tira comparativa + salida máquina
python fontid.py logo.png --api                    # nominación Claude (opt-in: envía crops a Anthropic)
```

- Scores: **overlaps crudos en [0,1]** con umbral de empate 0.03 — nunca porcentajes.
- Reporte de dos niveles: el cluster es confiable; el orden interno de un cluster
  empatado no, y el reporte lo marca (`EMPATE`).
- Prueba pesos `wght` 300–700 por familia y reporta el elegido.
- `--api` jamás se activa solo por tener `ANTHROPIC_API_KEY` — es opt-in explícito
  (los logos pueden ser material confidencial).
- El `--json` es una **emisión draft** (su esquema puede cambiar cuando la Fase B
  de recomposición firme sus requisitos — ver el spec).
````

- [ ] **Step 3: Verify and commit**

Run: `python -m pytest tests/ -q` → all pass.

```bash
git add requirements.txt README.md
git commit -m "docs: fontid Fase A usage, deps with platform caveats"
```

---

### Task 9: Corrida de aceptación sobre el logo real

**Files:**
- Modify: `docs/calibration/2026-06-05-logo-libre-mente.md`

- [ ] **Step 1: Full-auto run (OCR + pool 60 + pesos)**

```powershell
python fontid.py "C:\Users\simon\Desktop\logo_ale.jpeg" --preview
```

Expected: el OCR detecta "mente" e "INTEGRATIVE PSYCHOLOGY" (y probablemente NO "libre" — el aviso fijo lo declara); reporte de dos niveles con wght por candidata; previews junto al logo. Primera corrida fría: ~60-90s (descarga de ~60 familias × pesos, paralela).

- [ ] **Step 2: Las dos preguntas de aceptación**

1. **¿El probing de pesos resolvió la observación del gate?** — ¿la top-1 de "mente" ahora es una garalda en peso ligero (Cormorant Garamond 300?) y el preview se parece más al original que el del spike?
2. **¿El flujo automático encontró las regiones correctas sin --region?**

- [ ] **Step 3: Document in `docs/calibration/2026-06-05-logo-libre-mente.md`**

Append sección `## Fase A — corrida de aceptación (fecha)` con: reporte completo, wght elegidos, tiempos de la corrida fría/caliente, qué detectó/perdió el OCR, y la comparación con los resultados del spike (¿cambió el líder al sumar pesos?).

- [ ] **Step 4: Commit y push**

```bash
git add docs/calibration/2026-06-05-logo-libre-mente.md
git commit -m "docs: fontid Fase A acceptance run on libre-mente logo"
git push
```

- [ ] **Step 5: Presentar a Samuel** — el reporte, los previews y el veredicto de las dos preguntas. La aceptación de Fase A es su juicio.
