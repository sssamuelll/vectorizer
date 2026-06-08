# Spec A — Extracción de `recompose_core.py` — Plan de Implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sacar las funciones de compose compartido de `recompose.py` a un nuevo
`recompose_core.py` y dejar `recompose.py` como orquestador CLI delgado, **sin cambiar una
sola salida del CLI** (SVG byte-idéntico, stdout idéntico).

**Architecture:** Refactor green-to-green. La suite de 30 tests existente es la red de
seguridad: pasa antes y después de cada tarea. Una sola pieza nueva — `compose_hybrid_svg`
(+ `ComposeResult`) — levanta el cableado de compose que hoy vive inline en `main()` a una
función del core, dueña única de esa política (junta ③), para que el backend de Spec B no la
duplique. La frontera la cierra un test AST de superficie de imports extendido a ambos archivos.

**Tech Stack:** Python 3.14, pytest, cv2, numpy, fontTools, fontid/vectorize (intactos).
Sin dependencias nuevas, sin JS, sin backend.

**Spec:** `docs/superpowers/specs/2026-06-07-recompose-core-extraction-design.md`
**Maestro:** `docs/superpowers/specs/2026-06-07-recompose-web-app-design.md` (§3)

---

## Estructura de archivos

| archivo | responsabilidad | acción |
|---|---|---|
| `recompose_core.py` | compose compartido: funciones puras + `ComposeResult` + `compose_hybrid_svg` | **crear** |
| `recompose.py` | orquestador CLI replay (`--font`): parseo, costura/empate, presentación, `main` | **adelgazar** |
| `tests/test_recompose_core.py` | tests de las funciones del core | **crear** |
| `tests/test_recompose.py` | tests del CLI + AST de superficie extendido | **modificar** |
| `fontid.py`, `vectorize.py` | intactos | — |

**Dependencia unidireccional:** `recompose` → importa de → `recompose_core`. El core JAMÁS
importa de `recompose` (lo verifica el AST en la Tarea 4).

**Reparto de símbolos** (la regla: una función va al core solo si el backend la importará):

- **Al core:** `FontKeyError`, `SeamDecision`, `seam_decision`, `common_scale`,
  `glyph_transform`, `region_glyph_paths`, `resolve_ttf`, `calligraphy_paths`,
  `binary_ink_mask`, `compose_svg`; constantes `CALLIG_RDP`, `CALLIG_CHAIKIN`,
  `CALLIG_TENSION`, `MASK_PAD`, `COLOR_WARN_THRESHOLD`; **nuevas** `ComposeResult` +
  `compose_hybrid_svg`.
- **Se quedan en el CLI:** `_norm_key`, `parse_font_arg`, `resolve_font_choices`,
  `print_seam_report`, `print_correction_commands`, `_render_svg`, `write_preview`,
  `build_parser`, `main`; constantes `EXIT_NADA_QUE_RECOMPONER`, `EXIT_EMPATE_PENDIENTE`,
  `EXIT_FONT_KEY`.

---

## Task 1: Crear `recompose_core.py` y mover las funciones (sin cambio de comportamiento)

**Files:**
- Create: `recompose_core.py`
- Modify: `recompose.py:17-50` (imports + constantes) y eliminar las defs movidas
- Test: la suite existente `tests/test_recompose.py` (no se toca en esta tarea)

En esta tarea `main()` **sigue con el compose inline** y usa los nombres movidos; por eso
`recompose.py` los re-importa del core y `recompose.X` sigue resolviendo para los tests.

- [ ] **Step 1: Crear `recompose_core.py` con las funciones movidas verbatim**

Crear `recompose_core.py` con este encabezado, y a continuación **mover sin cambios** (copiar
verbatim desde `recompose.py`) estas definiciones, en este orden: `FontKeyError` (de
recompose.py:49-50), `_norm_key` **NO** (se queda en CLI), las constantes `CALLIG_RDP`,
`CALLIG_CHAIKIN`, `CALLIG_TENSION`, `MASK_PAD` (recompose.py:42-46) y `COLOR_WARN_THRESHOLD`
(recompose.py:40), `SeamDecision` (102-105), `seam_decision` (108-121), `common_scale`
(133-142), `glyph_transform` (145-153), `region_glyph_paths` (156-188), `resolve_ttf`
(191-210), `calligraphy_paths` (213-234), `binary_ink_mask` (237-242), `compose_svg` (245-268).

```python
#!/usr/bin/env python3
"""recompose_core.py — compose híbrido compartido (CLI y backend web).

Funciones puras que ambos orquestadores importan: resolución de TTF, glifos
desde TTF, caligrafía vectorizada, compositor SVG, y el cableado de compose
(compose_hybrid_svg) como dueño único de esa política.

Dependencia unidireccional: este módulo NO importa de recompose.py.
Superficie de import CERRADA (test AST la vigila):
  fontid:    download_family_weights
  vectorize: clean_binary_mask, extract_stroke_color, trace_contours
"""
import hashlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

from fontid import download_family_weights
from vectorize import clean_binary_mask, extract_stroke_color, trace_contours

# precondición una tinta (spec §7)
COLOR_WARN_THRESHOLD = 12

# caligrafía: ganadores del barrido de calibración
CALLIG_RDP = 0.8
CALLIG_CHAIKIN = 2
CALLIG_TENSION = 0.5
MASK_PAD = 6

# ── (a continuación, las definiciones movidas verbatim, en el orden de arriba) ──
```

- [ ] **Step 2: Adelgazar los imports y borrar las defs movidas en `recompose.py`**

Reemplazar el bloque de imports `recompose.py:17-46` (imports + constantes movidas) y borrar
las definiciones movidas (las líneas 40, 42-46, 49-50, 102-121, 133-268 quedan en el core).
`recompose.py` arranca así (mantiene `EXIT_*`, mantiene `_norm_key`/`parse_font_arg`/
`resolve_font_choices`, `print_*`, `_render_svg`/`write_preview`, `build_parser`, `main`):

```python
#!/usr/bin/env python3
"""recompose.py — Fase B v0.1 (replay puro), orquestador CLI sobre recompose_core.

Logo de UNA tinta → SVG híbrido. El core compartido vive en recompose_core.py;
aquí queda el CLI: parseo de --font, costura/empate, presentación, main.
Spec: docs/superpowers/specs/2026-06-07-recompose-core-extraction-design.md

Superficie de import CERRADA (test AST la vigila):
  recompose_core: lo que main() usa
  fontid:         analyze_regions, CACHE_DIR_DEFAULT
  vectorize:      load_image_bgr, count_effective_colors
"""
import argparse
import hashlib
import sys
from pathlib import Path

import cv2
import numpy as np

from recompose_core import (CALLIG_RDP, CALLIG_CHAIKIN, CALLIG_TENSION,
                            COLOR_WARN_THRESHOLD, MASK_PAD, FontKeyError,
                            SeamDecision, binary_ink_mask, calligraphy_paths,
                            common_scale, compose_svg, glyph_transform,
                            region_glyph_paths, resolve_ttf, seam_decision)
from fontid import CACHE_DIR_DEFAULT, analyze_regions
from vectorize import count_effective_colors, load_image_bgr

# exit codes (spec §7) — CLI-only
EXIT_NADA_QUE_RECOMPONER = 2
EXIT_EMPATE_PENDIENTE = 3
EXIT_FONT_KEY = 4
```

> Nota: en esta tarea `main()` aún usa el compose inline, así que importa `binary_ink_mask`,
> `calligraphy_paths`, `compose_svg`, `region_glyph_paths`, `resolve_ttf` (todos usados en
> recompose.py:432-454). También `common_scale`/`glyph_transform`/`SeamDecision` para que los
> tests que hacen `recompose.X` sigan resolviendo. `hashlib` se mantiene (main lo usa inline).
> `extract_stroke_color` lo usa main inline (línea 453): agrégalo al import de vectorize en
> recompose.py en ESTA tarea → `from vectorize import (count_effective_colors,
> extract_stroke_color, load_image_bgr)`. (Se quita en la Tarea 3.)

- [ ] **Step 3: Correr la suite completa — debe pasar sin cambios**

Run: `python -m pytest tests/test_recompose.py -q`
Expected: PASS (30 passed, los skip de TTF/red según caché). Cero cambios de comportamiento.

- [ ] **Step 4: Verificar que no hay import circular**

Run: `python -c "import recompose_core; import recompose; print('ok')"`
Expected: imprime `ok` sin ImportError.

- [ ] **Step 5: Commit**

```bash
git add recompose_core.py recompose.py
git commit -m "refactor(recompose): extrae recompose_core.py (funciones movidas verbatim)"
```

---

## Task 2: Añadir `ComposeResult` + `compose_hybrid_svg` al core (con su test)

**Files:**
- Modify: `recompose_core.py` (añadir al final, antes de nada de `__main__`)
- Create: `tests/test_recompose_core.py`

`main()` **no se toca todavía**. Esta tarea añade la función y prueba que reproduce el bloque
inline, para que la Tarea 3 (refactor de main) sea un swap seguro.

- [ ] **Step 1: Escribir el test de `compose_hybrid_svg` (falla: no existe)**

Crear `tests/test_recompose_core.py`:

```python
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


@pytest.mark.skipif(not TTF_TEST.exists(), reason="TTF de caché no disponible")
def test_compose_hybrid_svg_reproduce_el_inline():
    """compose_hybrid_svg produce el mismo SVG que el cableado inline del CLI
    para una región type con líder — gate del levantamiento (Spec A §3)."""
    img = _logo_sintetico()
    r = _region(text="abc", bbox=(50, 60, 250, 115), n_glyphs=3,
                classification="type",
                ranking=_rank(("Cormorant Garamond", 500, 0.8, False)))
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
```

- [ ] **Step 2: Correr el test — debe fallar**

Run: `python -m pytest tests/test_recompose_core.py -q`
Expected: FAIL con `AttributeError: module 'recompose_core' has no attribute 'compose_hybrid_svg'`.

- [ ] **Step 3: Implementar `ComposeResult` + `compose_hybrid_svg` en `recompose_core.py`**

Añadir al final de `recompose_core.py` (después de `compose_svg`):

```python
@dataclass
class ComposeResult:
    """Salida del compose híbrido — interfaz para CLI (imprime stats) y backend
    (devuelve svg + provenance)."""
    svg_text: str
    ink: str
    callig_count: int
    glyph_count: int
    provenance: list      # [str] «familia:peso sha256:<hex>»
    mask_boxes: list      # [bbox] de las regiones recompuestas


def compose_hybrid_svg(img_bgr, regions, choices, recomp_idx, sigma, cache_dir):
    """Cableado de compose compartido (CLI y backend). Dado choices YA resueltos
    {idx: (family, wght)} y los índices a recomponer, compone el SVG híbrido.
    Dueño único de la política de compose (junta ③). Lanza FontKeyError si el TTF
    falla — el orquestador decide cómo presentarlo (CLI: exit 4; backend: HTTP).

    Levantado verbatim de recompose.py:427-454 (el bloque inline de main)."""
    cache_dir = Path(cache_dir)
    glyph_pairs = []
    mask_boxes = []
    provenance = []
    for i in recomp_idx:
        r = regions[i]
        family, wght = choices[i]
        ttf = resolve_ttf(family, wght, cache_dir)
        sha = hashlib.sha256(ttf.read_bytes()).hexdigest()[:16]
        provenance.append(f"{family}:{wght} sha256:{sha}")
        chars = [c for c in r.text if not c.isspace()]
        glyph_pairs.extend(region_glyph_paths(ttf, chars, r.glyph_boxes, family))
        mask_boxes.append(r.bbox)
    h, w = img_bgr.shape[:2]
    callig = calligraphy_paths(img_bgr, mask_boxes, sigma=sigma)
    ink = extract_stroke_color(img_bgr, binary_ink_mask(img_bgr))
    svg_text = compose_svg(w, h, ink, callig, glyph_pairs, provenance=provenance)
    return ComposeResult(svg_text, ink, len(callig), len(glyph_pairs),
                         provenance, mask_boxes)
```

- [ ] **Step 4: Correr el test — debe pasar**

Run: `python -m pytest tests/test_recompose_core.py -q`
Expected: PASS (2 passed, o 1 passed + 1 skipped si falta el TTF de caché).

- [ ] **Step 5: Commit**

```bash
git add recompose_core.py tests/test_recompose_core.py
git commit -m "feat(recompose-core): compose_hybrid_svg + ComposeResult (dueno del cableado)"
```

---

## Task 3: Refactorizar `main()` para usar `compose_hybrid_svg`; mover los tests del core

**Files:**
- Modify: `recompose.py:426-462` (el bloque de compose de `main`) + imports
- Modify: `tests/test_recompose.py` (eliminar los tests de funciones movidas)
- Modify: `tests/test_recompose_core.py` (recibir los tests movidos)

- [ ] **Step 1: Reemplazar el bloque inline de compose en `main()`**

En `recompose.py`, reemplazar el bloque `recompose.py:426-462` (desde `# compositor` hasta
justo antes de `out_path = ...`) por:

```python
    # compositor (cableado en el core — dueño único, junta ③)
    cache_dir = Path(args.cache_dir)
    try:
        res = compose_hybrid_svg(img, regions, choices, recomp_idx,
                                 args.contour_sigma, cache_dir)
    except FontKeyError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(EXIT_FONT_KEY)
    svg_text = res.svg_text
    final_choices = {i: choices[i] for i in recomp_idx}

    out_path = (Path(args.output) if args.output
                else Path(args.input).with_name(
                    Path(args.input).stem + "_recompuesto.svg"))
    out_path.write_text(svg_text, encoding="utf-8")
    print(f"\n  [OK] SVG híbrido: {out_path}")
    print(f"       Tinta: {res.ink} | caligrafía: {res.callig_count} contornos | "
          f"glifos: {res.glyph_count}")

    preview = write_preview(img, svg_text, res.mask_boxes,
                            out_path.with_name(out_path.stem + "_preview.png"))
```

> El resto de `main()` (el `if preview:`, `print_correction_commands`, `raise SystemExit(0)`)
> queda igual. La salida es byte-idéntica: mismos ink/contornos/glifos, mismo SVG.

- [ ] **Step 2: Quitar los imports que `main()` ya no usa directamente en `recompose.py`**

`main()` ya no usa `binary_ink_mask`, `calligraphy_paths`, `compose_svg`, `region_glyph_paths`,
`resolve_ttf`, `common_scale`, `glyph_transform`, `extract_stroke_color`, `hashlib` ni `SeamDecision`
directamente. Ajustar los imports de `recompose.py` a lo que `main()` y las funciones CLI sí usan:

```python
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

from recompose_core import (COLOR_WARN_THRESHOLD, FontKeyError,
                            compose_hybrid_svg, seam_decision)
from fontid import CACHE_DIR_DEFAULT, analyze_regions
from vectorize import count_effective_colors, load_image_bgr
```

> `seam_decision` se queda importado (main lo usa para la costura). `FontKeyError` también
> (main lo atrapa; `resolve_font_choices` lo lanza). `COLOR_WARN_THRESHOLD` (main: aviso color).
> `cv2`/`numpy` siguen (los usan `_render_svg`/`write_preview`). `CALLIG_*`/`MASK_PAD` se quitan
> (solo el core los usa).

- [ ] **Step 3: Mover los tests de funciones movidas a `tests/test_recompose_core.py`**

**Cortar** de `tests/test_recompose.py` y **pegar** en `tests/test_recompose_core.py` (cambiando
el prefijo `recompose.` → `recompose_core.` en el cuerpo de cada uno) estos tests:
`test_costura_type_se_recompone`, `test_costura_handwriting_se_vectoriza`,
`test_costura_type_sin_ranking_se_vectoriza`, `test_seam_type_con_font_recompone_sin_ranking`,
`test_common_scale_mediana`, `test_glyph_transform_alinea_centro_y_fondo`,
`test_region_glyph_paths_con_ttf_real`, `test_region_glyph_paths_char_sin_glifo`,
`test_region_glyph_paths_ttf_corrupto`, `test_resolve_ttf_cache_hit`,
`test_resolve_ttf_descarga_on_demand`, `test_resolve_ttf_peso_inexistente_error_duro`,
`test_resolve_ttf_rechaza_familia_con_ruta`, `test_calligraphy_paths_excluye_regiones_enmascaradas`,
`test_compose_svg_estructura`, `test_compose_svg_con_provenance`.

> Ojo a dos detalles al pegar: (1) los `monkeypatch.setattr(recompose, "download_family_weights",
> ...)` pasan a `monkeypatch.setattr(recompose_core, "download_family_weights", ...)` (resolve_ttf
> vive en el core). (2) `recompose.FontKeyError` → `recompose_core.FontKeyError`. Las constantes
> `CACHE`/`TTF_TEST` ya están definidas en `test_recompose_core.py` (Tarea 2) — no duplicar.

`test_reporte_costura_siempre_lista_todas` **se queda** en `test_recompose.py` (prueba
`print_seam_report`, que es CLI; usa `recompose.seam_decision`, que resuelve por el import).

- [ ] **Step 4: Correr ambas suites — verde**

Run: `python -m pytest tests/test_recompose.py tests/test_recompose_core.py -q`
Expected: PASS. El total de tests es el mismo que antes + los 2 de `compose_hybrid_svg`;
ninguno perdido, ninguno duplicado.

- [ ] **Step 5: Verificar byte-identidad sobre el logo sintético (happy path de main)**

Run: `python -m pytest tests/test_recompose.py::test_main_camino_feliz_sin_empate -v`
Expected: PASS (o skip si falta TTF). El SVG sigue teniendo `class="ink"`, `class="type"`,
`TTF provenance`, y el preview se escribe — comportamiento de main intacto.

- [ ] **Step 6: Commit**

```bash
git add recompose.py tests/test_recompose.py tests/test_recompose_core.py
git commit -m "refactor(recompose): main() usa compose_hybrid_svg; tests del core migran"
```

---

## Task 4: Extender el test AST de superficie a `recompose_core.py`

**Files:**
- Modify: `tests/test_recompose.py` (el bloque `ALLOWED_INTERNAL_IMPORTS` +
  `test_superficie_de_imports_cerrada`, líneas 370-396)

- [ ] **Step 1: Reemplazar el test AST por la versión de dos archivos**

En `tests/test_recompose.py`, reemplazar `ALLOWED_INTERNAL_IMPORTS` (370-376) y
`test_superficie_de_imports_cerrada` (379-396) por:

```python
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
```

- [ ] **Step 2: Correr el test AST — debe pasar**

Run: `python -m pytest tests/test_recompose.py::test_superficie_de_imports_cerrada -v`
Expected: PASS. Si falla, lee la violación: o un símbolo cayó en el archivo equivocado
(muévelo) o el allowlist necesita el símbolo (con justificación en el spec).

- [ ] **Step 3: Correr la suite completa**

Run: `python -m pytest tests/ -q`
Expected: PASS (todos los tests de recompose + core + el resto del repo intactos).

- [ ] **Step 4: Commit**

```bash
git add tests/test_recompose.py
git commit -m "test(recompose): AST de superficie cierra recompose.py Y recompose_core.py"
```

---

## Task 5: Gate de aceptación — el CLI sigue dando byte-idéntico (0px)

**Files:** ninguno (verificación manual con assets fuera del repo — el logo de Ale es
material de cliente y vive en `C:\Users\simon\Desktop\Ale\`).

Este es el **gate de merge** de Spec A (spec §5), no un test unitario: confirma que el refactor
no cambió un byte de la salida real sobre el logo de Ale.

- [ ] **Step 1: Generar el SVG con el CLI refactorizado**

Run (PowerShell):
```powershell
python recompose.py "C:\Users\simon\Desktop\Ale\logo_ale.jpeg" `
  -o "$env:TEMP\ale_postrefactor.svg" `
  --font "mente=Nanum Myeongjo:400" `
  --font "INTEGRATIVE PSYCHOLOGY=STIX Two Text:600" `
  --contour-sigma 2
```
Expected: escribe `ale_postrefactor.svg`, exit 0, stdout con la costura + `[OK] SVG híbrido`.

- [ ] **Step 2: Byte-comparar contra el producto pre-refactor (logo_ale_v01.svg)**

Run (PowerShell):
```powershell
if ((Get-FileHash "$env:TEMP\ale_postrefactor.svg").Hash -eq `
    (Get-FileHash "C:\Users\simon\Desktop\Ale\logo_ale_v01.svg").Hash) {
  "BYTE-IDENTICO - gate verde"
} else { "DIVERGE - el refactor cambio la salida, revisar" }
```
Expected: `BYTE-IDENTICO - gate verde`.

> Si los SHA difieren pero el `git diff` del SVG es solo el comentario de provenance con un
> sha distinto (caché de TTF actualizada upstream), regenerá `logo_ale_v01.svg` desde
> `main` (pre-refactor) con el mismo comando y compará de nuevo: el refactor no debe cambiar
> NADA salvo lo que cambie la caché. Cualquier diferencia en paths `.ink` o `.type` es un fallo
> del refactor.

- [ ] **Step 3: Marcar Spec A listo para PR**

Si el gate es verde y `python -m pytest tests/ -q` pasa, Spec A está completo. Abrir PR de la
rama `recompose-core-extraction` a `main`.

---

## Self-Review (hecho al escribir el plan)

- **Cobertura del spec:** §1 objetivo → todas las tareas. §2 regla de partición → reparto de
  símbolos + Tarea 1/3. §3 `compose_hybrid_svg` → Tarea 2/3. §4 allowlists → Tarea 4. §5
  aceptación byte-idéntica + reparto de tests → Tarea 3 (tests) + Tarea 5 (0px). §6 no-goals →
  respetados (cero backend/JS/deps). §7 riesgos → el gate byte-idéntico (Tarea 5) cubre el
  principal; el AST (Tarea 4) cubre los símbolos mal ubicados; el `import` check cubre el
  circular.
- **Placeholders:** ninguno. Los moves citan rangos de línea exactos; el código nuevo
  (`ComposeResult`, `compose_hybrid_svg`, el test AST, los tests de core) está completo.
- **Consistencia de tipos:** `compose_hybrid_svg(img_bgr, regions, choices, recomp_idx, sigma,
  cache_dir) -> ComposeResult`; main desempaqueta `res.svg_text/.ink/.callig_count/.glyph_count/
  .mask_boxes` — coinciden con los campos de `ComposeResult`. `resolve_ttf(family, wght,
  cache_dir)` sin cambio de firma. Allowlist del core (Tarea 4) == imports reales del core
  (Tarea 1/2).
```
