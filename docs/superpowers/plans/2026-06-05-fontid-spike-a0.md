# Spike Fase A.0: Aproximación de Fuentes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir el spike mínimo de `fontid.py` que responde con un gate falsable: ¿el matching glifo-a-glifo rankea el cluster garalda arriba para "mente" e "INTEGRATIVE PSYCHOLOGY" del logo real?

**Architecture:** Script nuevo `fontid.py` (espejo del estilo de `vectorize.py`, importa solo `load_image_bgr`). Cuatro piezas: segmentación por componentes conexos (sin fusión vertical — límite declarado del spike), descarga validada de TTFs de Google Fonts (UA default, escritura atómica), matching con factor de escala COMÚN (preserva proporciones discriminantes) + IoU por glifo con media truncada, y reporte honesto con umbral de empate 0.03. Pool fijo: 20 garaldas + 4 controles negativos.

**Tech Stack:** Python 3.14, OpenCV, numpy, Pillow (ya instaladas), urllib stdlib. SIN winocr (el OCR es Fase A), SIN vtracer.

**Spec:** `docs/superpowers/specs/2026-06-05-font-identification-design.md` (v2, sección "Fase A.0 — Spike"). Los "hechos runtime" referenciados son de ese spec.

**Regiones conocidas del logo real** (`C:\Users\simon\Desktop\logo_ale.jpeg`, 1507×1044):
- "mente": `--region 450,600,1050,770`
- "INTEGRATIVE PSYCHOLOGY": `--region 270,755,1230,855`

---

## File Structure

| archivo | responsabilidad |
|---|---|
| `fontid.py` (crear) | Todo el spike: pools, descarga TTF, segmentación, matching, reporte, CLI. ~250 líneas. |
| `tests/test_fontid.py` (crear) | Test de cordura del matching (Georgia gana) + tests de validación de descarga. |
| `docs/calibration/2026-06-05-logo-libre-mente.md` (modificar, Task 4) | Resultado del gate del spike. |

`vectorize.py` NO se modifica.

---

### Task 1: Núcleo de matching (segmentación + render + IoU con factor común)

**Files:**
- Create: `fontid.py`
- Create: `tests/test_fontid.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_fontid.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_fontid.py -v`
Expected: 3 ERROR/FAIL with `ModuleNotFoundError: No module named 'fontid'`

- [ ] **Step 3: Create `fontid.py` with the matching core**

```python
#!/usr/bin/env python3
"""
Spike Fase A.0 — Aproximación de fuentes tipográficas (Google Fonts).

NO identifica fuentes: aproxima. Encuentra la alternativa más cercana
dentro de Google Fonts. Ver docs/superpowers/specs/2026-06-05-font-identification-design.md

Uso:
    python fontid.py logo.png --region x0,y0,x1,y1 --text "mente"
"""

import argparse
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from vectorize import load_image_bgr

# ═══════════════════════════════════════════════════════════════════
# 1. SEGMENTACIÓN (sin fusión vertical — límite declarado del spike:
#    parte minúsculas con punto i/j y acentos; las palabras del caso
#    motivador no los tienen. La fusión es requisito de Fase A.)
# ═══════════════════════════════════════════════════════════════════

def _tight(mask):
    """Recorta una máscara booleana a su contenido."""
    ys, xs = np.where(mask)
    return mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def segment_glyphs(crop_bgr, min_area=4):
    """Binariza (Otsu directo — SIN clean_binary_mask, que destruye
    serifas/puntos por diseño) y devuelve las máscaras de los glifos
    como componentes conexos ordenados por x."""
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    flag = cv2.THRESH_BINARY_INV if np.mean(gray) > 127 else cv2.THRESH_BINARY
    _, binary = cv2.threshold(gray, 0, 255, flag | cv2.THRESH_OTSU)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(
        (binary > 0).astype(np.uint8), connectivity=8)
    comps = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < min_area:
            continue
        comps.append((x, labels[y:y + h, x:x + w] == i))
    comps.sort(key=lambda t: t[0])
    return [m for _, m in comps]


# ═══════════════════════════════════════════════════════════════════
# 2. RENDER + MATCHING (métrica del spec: factor de escala COMÚN —
#    las proporciones relativas entre glifos sobreviven y los
#    desajustes de tamaño penalizan el IoU. Solo la posición se
#    normaliza (centroide): el tracking es decisión del logo, no
#    de la fuente.)
# ═══════════════════════════════════════════════════════════════════

def render_glyph(ch, font):
    """Renderiza un carácter como máscara booleana recortada, o None."""
    bbox = font.getbbox(ch)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    if w <= 0 or h <= 0:
        return None
    img = Image.new("L", (w + 8, h + 8), 0)
    ImageDraw.Draw(img).text((4 - bbox[0], 4 - bbox[1]), ch, fill=255, font=font)
    arr = np.array(img) > 127
    if not arr.any():
        return None
    return _tight(arr)


def _iou_centroid(a, b):
    """IoU de dos máscaras alineadas por centroide en un canvas común
    (tamaño 2*max para que el pegado nunca recorte)."""
    H = 2 * max(a.shape[0], b.shape[0]) + 4
    W = 2 * max(a.shape[1], b.shape[1]) + 4

    def centered(m):
        c = np.zeros((H, W), dtype=bool)
        ys, xs = np.where(m)
        oy = int(round(H / 2 - ys.mean()))
        ox = int(round(W / 2 - xs.mean()))
        c[oy:oy + m.shape[0], ox:ox + m.shape[1]] = m
        return c

    A, B = centered(a), centered(b)
    union = np.logical_or(A, B).sum()
    if union == 0:
        return 0.0
    return float(np.logical_and(A, B).sum() / union)


def match_candidate(crop_glyphs, chars, ttf_path, base_size=96):
    """Score de una candidata contra los glifos del crop.

    Devuelve overlap en [0,1] (media truncada de IoU por glifo) o None
    si la región es insuficiente (<2 glifos) o el render falla.
    - ≥4 glifos → se descarta el peor (robustez);
    - 2-3 glifos → media simple;
    - <2 glifos → None ("insuficiente para matching").
    """
    if len(crop_glyphs) < 2 or len(crop_glyphs) != len(chars):
        return None
    font = ImageFont.truetype(str(ttf_path), base_size)
    rendered = [render_glyph(c, font) for c in chars]
    if any(r is None for r in rendered):
        return None

    # UN factor común, anclado a la altura mediana (spec, métrica del spike)
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
        ious = ious[1:]  # descarta el peor glifo
    return float(np.mean(ious))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_fontid.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add fontid.py tests/test_fontid.py
git commit -m "feat(spike): fontid matching core — common-scale glyph IoU"
```

---

### Task 2: Descarga validada de TTFs de Google Fonts

**Files:**
- Modify: `fontid.py` (nueva sección tras el matching)
- Test: `tests/test_fontid.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_fontid.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_fontid.py -v -k validate`
Expected: 2 FAIL with `AttributeError: module 'fontid' has no attribute 'validate_ttf'`

- [ ] **Step 3: Implement download + validation**

Append to `fontid.py`:

```python
# ═══════════════════════════════════════════════════════════════════
# 3. DESCARGA DE TTF (hecho runtime 3 del spec: el UA por defecto de
#    urllib entrega TTF directo — el "truco UA legacy" del v1 estaba
#    invertido y NO se usa. Validación antes de cachear + escritura
#    atómica: nunca queda un TTF a medias o corrupto en caché.)
# ═══════════════════════════════════════════════════════════════════

GF_CSS2 = "https://fonts.googleapis.com/css2?family={}"
TTF_MAGICS = (b"\x00\x01\x00\x00", b"OTTO", b"true")


def validate_ttf(path):
    """Magic bytes + apertura efectiva con Pillow. True si es usable."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return False
    if not any(data.startswith(m) for m in TTF_MAGICS):
        return False
    try:
        ImageFont.truetype(str(path), 24)
    except Exception:
        return False
    return True


def download_ttf(family, cache_dir):
    """Descarga el TTF regular de una familia GF a la caché.

    Devuelve la ruta cacheada, o None si la red/validación falla
    (el caller cuenta las omitidas y sigue — spec, tabla de errores).
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(exist_ok=True)
    dest = cache_dir / (family.replace(" ", "_") + ".ttf")
    if dest.exists():
        return dest
    try:
        url = GF_CSS2.format(urllib.parse.quote_plus(family))
        css = urllib.request.urlopen(url, timeout=20).read().decode("utf-8")
        m = re.search(r"url\((https://[^)]+\.ttf)\)", css)
        if not m:
            return None
        data = urllib.request.urlopen(m.group(1), timeout=30).read()
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    tmp = dest.with_suffix(".tmp")
    tmp.write_bytes(data)
    if not validate_ttf(tmp):
        tmp.unlink(missing_ok=True)
        return None
    os.replace(tmp, dest)  # escritura atómica (spec)
    return dest
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_fontid.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add fontid.py tests/test_fontid.py
git commit -m "feat(spike): validated atomic TTF download from Google Fonts"
```

---

### Task 3: Pools, ranking, reporte y CLI

**Files:**
- Modify: `fontid.py` (sección final)
- Test: `tests/test_fontid.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_fontid.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_fontid.py -v -k "cli or ties or pool"`
Expected: 3 FAIL with `AttributeError`

- [ ] **Step 3: Implement pools, ranking, report, CLI**

Append to `fontid.py`:

```python
# ═══════════════════════════════════════════════════════════════════
# 4. POOLS, RANKING Y REPORTE
# ═══════════════════════════════════════════════════════════════════

SPIKE_POOL = [
    "Cormorant Garamond", "EB Garamond", "Cormorant SC", "Crimson Pro",
    "Crimson Text", "Sorts Mill Goudy", "Gilda Display", "Playfair Display",
    "Lora", "PT Serif", "Libre Baskerville", "Source Serif 4",
    "Noto Serif Display", "Cardo", "Spectral", "Domine",
    "Frank Ruhl Libre", "Marcellus", "Cinzel", "Old Standard TT",
]
# Controles negativos (sans/display/script): sin ellos la separación del
# cluster serif sería inmedible — son la línea base del gate (spec A.0).
CONTROLES = ["Roboto", "Montserrat", "Oswald", "Pacifico"]

TIE_DELTA = 0.03  # hecho runtime 6 del spec: margen serif-vs-serif real 0.027

CORPUS_NOTE = (
    "Corpus: Google Fonts. Si la fuente original es comercial, esto es la\n"
    "alternativa libre más cercana — no una identificación."
)


def tie_flags(ranked):
    """[(familia, overlap)] ordenado desc → [bool] EMPATE-con-el-líder."""
    if not ranked:
        return []
    leader = ranked[0][1]
    return [i > 0 and (leader - s) < TIE_DELTA for i, (_, s) in enumerate(ranked)]


def rank_region(crop_bgr, text, cache_dir):
    """Devuelve (ranked, controls, skipped, mismatch) para una región.

    mismatch: None, o (n_glifos, n_chars) si la segmentación no cuadra
    con el texto — la región se reporta y no se rankea.
    """
    glyphs = segment_glyphs(crop_bgr)
    chars = [c for c in text if not c.isspace()]
    if len(glyphs) != len(chars):
        return None, None, 0, (len(glyphs), len(chars))
    ranked, controls, skipped = [], [], 0
    for fam in SPIKE_POOL + CONTROLES:
        ttf = download_ttf(fam, cache_dir)
        if ttf is None:
            skipped += 1
            continue
        score = match_candidate(glyphs, chars, ttf)
        if score is None:
            continue
        (controls if fam in CONTROLES else ranked).append((fam, score))
    ranked.sort(key=lambda t: -t[1])
    controls.sort(key=lambda t: -t[1])
    return ranked, controls, skipped, None


def print_region_report(idx, text, ranked, controls, skipped, mismatch):
    print(f"\n[REGIÓN {idx}] \"{text}\"")
    if mismatch:
        print(f"  segmentación≠texto ({mismatch[0]} glifos vs {mismatch[1]} chars)"
              f" — no se rankea. ¿Puntos/acentos? (límite del spike)")
        return
    if not ranked:
        print("  sin candidatas rankeables")
        return
    ties = tie_flags(ranked)
    best_control = controls[0][1] if controls else 0.0
    sep = ranked[0][1] - best_control
    print(f"  separación del cluster vs controles: {sep:.3f} "
          f"({'OK' if sep > 0.1 else 'DÉBIL'} — gate condición 1)")
    prev = None
    for i, ((fam, s), tie) in enumerate(zip(ranked[:5], ties[:5]), 1):
        delta = f"   Δ {prev - s:.3f}" if prev is not None else ""
        mark = "  → EMPATE con el líder" if tie else ""
        print(f"  {i}. {fam:<22s} overlap {s:.3f}{delta}{mark}")
        prev = s
    for fam, s in controls:
        print(f"  [control] {fam:<14s} overlap {s:.3f}")
    if skipped:
        print(f"  ({skipped} candidatas omitidas por red/validación)")


# ═══════════════════════════════════════════════════════════════════
# 5. CLI
# ═══════════════════════════════════════════════════════════════════

def build_parser():
    p = argparse.ArgumentParser(
        description="Spike A.0 — aproximación de fuentes (Google Fonts). "
                    "NO identifica: aproxima.")
    p.add_argument("input", help="Imagen del logo")
    p.add_argument("--region", action="append", required=True,
                   help="x0,y0,x1,y1 (repetible, pareado con --text)")
    p.add_argument("--text", action="append", required=True,
                   help="Texto de la región (repetible, pareado con --region)")
    p.add_argument("--cache-dir", default="ttf_cache",
                   help="Caché de TTFs (default: ./ttf_cache)")
    return p


def validate_args(args):
    if len(args.region) != len(args.text):
        sys.exit(f"error: --region ({len(args.region)}) y --text "
                 f"({len(args.text)}) deben ir pareados posicionalmente")


def main():
    args = build_parser().parse_args()
    validate_args(args)
    img = load_image_bgr(args.input)
    if img is None:
        raise ValueError(f"No se pudo cargar: {args.input}")
    print(CORPUS_NOTE)
    for i, (reg, text) in enumerate(zip(args.region, args.text), 1):
        try:
            x0, y0, x1, y1 = (int(v) for v in reg.split(","))
        except ValueError:
            sys.exit(f"error: región inválida {reg!r} (formato x0,y0,x1,y1)")
        ranked, controls, skipped, mismatch = rank_region(
            img[y0:y1, x0:x1], text, args.cache_dir)
        print_region_report(i, text, ranked, controls, skipped, mismatch)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the full suite and CLI smoke**

Run: `python -m pytest tests/test_fontid.py -v`
Expected: 8 PASS

Run: `python fontid.py --help`
Expected: ayuda con `--region`, `--text`, `--cache-dir`, sin traceback.

- [ ] **Step 5: Add `ttf_cache/` to `.gitignore`**

Append line `ttf_cache/` to `.gitignore`.

- [ ] **Step 6: Commit**

```bash
git add fontid.py tests/test_fontid.py .gitignore
git commit -m "feat(spike): fontid CLI with fixed pool, controls, tie-aware report"
```

---

### Task 4: La corrida del spike — evidencia del gate

**Files:**
- Modify: `docs/calibration/2026-06-05-logo-libre-mente.md` (nueva sección al final)

- [ ] **Step 1: Run the spike against the real logo**

```powershell
python fontid.py "C:\Users\simon\Desktop\logo_ale.jpeg" `
  --region 450,600,1050,770 --text "mente" `
  --region 270,755,1230,855 --text "INTEGRATIVE PSYCHOLOGY"
```

Expected: reporte con dos regiones, top-5 con overlaps y EMPATES, controles al final, línea de separación del cluster. La primera corrida descarga ~24 TTFs (~30s); las siguientes usan `./ttf_cache/`.

- [ ] **Step 2: Generate visual evidence for gate condition 2 (juicio de Samuel)**

```powershell
python -c "
from PIL import Image, ImageDraw, ImageFont
import cv2, numpy as np, fontid as fi
img = fi.load_image_bgr(r'C:\Users\simon\Desktop\logo_ale.jpeg')
crop = img[600:770, 450:1050]
# renderiza 'mente' con la top-1 del reporte (ajustar el nombre al resultado real)
top1 = 'Cormorant_Garamond'   # <- AJUSTAR al ganador real del Step 1
font = ImageFont.truetype(f'ttf_cache/{top1}.ttf', 120)
bbox = font.getbbox('mente')
ren = Image.new('RGB', (bbox[2]-bbox[0]+40, bbox[3]-bbox[1]+40), (255,255,255))
ImageDraw.Draw(ren).text((20-bbox[0], 20-bbox[1]), 'mente', fill=(135,177,164), font=font)
ren_np = cv2.cvtColor(np.array(ren), cv2.COLOR_RGB2BGR)
h = crop.shape[0]
ren_np = cv2.resize(ren_np, (int(ren_np.shape[1]*h/ren_np.shape[0]), h))
strip = cv2.hconcat([crop, np.full((h,20,3),255,np.uint8), ren_np])
cv2.imwrite(r'C:\Users\simon\Desktop\fontid_gate_mente.png', strip)
print('gate strip OK')
"
```

Expected: `C:\Users\simon\Desktop\fontid_gate_mente.png` — crop original a la izquierda, top-1 renderizada a la derecha, para juicio visual.

- [ ] **Step 3: Evaluate gate condition 1 (separación medible)**

Del output del Step 1: la línea `separación del cluster vs controles` debe ser > 0.1 en ambas regiones (orden de 0.2 esperado por el hecho runtime 6). Anotar los números exactos.

- [ ] **Step 4: Document the gate result in the calibration doc**

Append to `docs/calibration/2026-06-05-logo-libre-mente.md` una sección `## Spike A.0 — resultado del gate (fecha)` con: el top-5 de cada región (overlaps y empates), la separación vs controles, el conteo de glifos segmentados, lo que falló si algo falló, y el veredicto del gate (pendiente del juicio visual de Samuel para la condición 2).

- [ ] **Step 5: Commit**

```bash
git add docs/calibration/2026-06-05-logo-libre-mente.md
git commit -m "docs: spike A.0 gate evidence on libre-mente logo"
```

- [ ] **Step 6: Present gate evidence to Samuel**

Mostrar: el reporte de las dos regiones, la tira visual, y los números de separación. **La condición 2 del gate es su juicio — el spike no se autodeclara aprobado.** Si el gate pasa → Fase A se planifica. Si falla → el aprendizaje queda en docs/calibration/ y Fase A no se construye (spec, sección "Gate de salida del spike").
