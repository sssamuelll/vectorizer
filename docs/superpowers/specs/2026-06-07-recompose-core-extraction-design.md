# Spec A — extracción de `recompose_core.py` (diseño)

**Fecha:** 2026-06-07
**Estado:** spec hijo de `2026-06-07-recompose-web-app-design.md` (maestro v2, §3).
Primer entregable del arco web. **Cero JS, cero backend, cero cambio de comportamiento.**
**Ship objetivo:** viernes 12-jun-2026.
**Aceptación dura:** el CLI sigue produciendo el **SVG byte-idéntico** de hoy → XOR 0px
contra `logo_ale_perfecto.svg`. Un refactor con gate de no-regresión.

---

## 1. Objetivo (una línea)

Sacar las funciones de **compose compartido** de `recompose.py` a `recompose_core.py`, dejar
`recompose.py` como orquestador CLI delgado que las importa, y extender el test AST de superficie
— **sin cambiar una sola salida del CLI**. Es el prerrequisito de Spec B (el backend importará el
core); su único trabajo es preparar la frontera sin arriesgar la aceptación 0px ya ganada.

## 2. La regla de partición (Vex + Voronov, junta §5)

**Una función va a `recompose_core.py` solo si el backend la va a importar.** Lo que solo el CLI
toca — la sintaxis de la cadena `--font`, la presentación a stdout, el preview PNG — **no es core,
es CLI**. Mover por simetría estética infla la superficie compartida y el AST que la vigila.

| símbolo (recompose.py hoy) | destino | por qué |
|---|---|---|
| `compose_svg` | **core** | compositor; backend `/compose` lo usa |
| `region_glyph_paths` | **core** | glifos TTF; backend `/candidate` + `/compose` |
| `common_scale`, `glyph_transform` | **core** | internas de `region_glyph_paths` |
| `resolve_ttf` | **core** | resolución TTF on-demand; backend la usa |
| `calligraphy_paths` | **core** | caligrafía; backend `/compose` |
| `binary_ink_mask` | **core** | máscara de tinta para el color; `/compose` |
| `seam_decision`, `SeamDecision` | **core** | la costura es un **hecho** que el backend reporta al frontend (junta ③) |
| `FontKeyError` | **core** | excepción que ambos orquestadores lanzan/atrapan |
| `CALLIG_RDP/CHAIKIN/TENSION`, `MASK_PAD`, `COLOR_WARN_THRESHOLD` | **core** | constantes que acompañan a sus funciones / umbral compartido |
| **`compose_hybrid_svg`** (NUEVA, §3) | **core** | dueño único del cableado de compose |
| `parse_font_arg`, `resolve_font_choices`, `_norm_key` | **CLI** | parseo de la sintaxis `clave=Familia:wght` — la web manda datos estructurados, no strings |
| `print_seam_report`, `print_correction_commands` | **CLI** | presentación a stdout |
| `write_preview`, `_render_svg` | **CLI** | preview PNG con resvg — la web renderiza SVG nativo, no lo necesita |
| `build_parser`, `main`, `EXIT_*` | **CLI** | entrada y códigos de salida del CLI |

`analyze_regions`, `count_effective_colors`, `load_image_bgr` **no se mueven** — viven en
`fontid`/`vectorize` y ambos orquestadores los importan de su origen (no se re-exportan por el core).

## 3. La única pieza más-que-mecánica: `compose_hybrid_svg`

Hoy el cableado de compose vive **inline en `main()`** (recompose.py:426-454): por cada región a
recomponer resuelve el TTF, junta glyph_pairs/mask_boxes/provenance, vectoriza la caligrafía,
extrae la tinta, y llama `compose_svg`. Spec B necesitará ese **mismo** cableado en `/api/compose`.
Si se queda inline en `main()`, B lo **duplica** — exactamente la política sin dueño que la junta ③
marcó. Por eso se levanta a una función del core, **idéntica línea por línea** al bloque actual:

```python
def compose_hybrid_svg(img_bgr, regions, choices, recomp_idx, sigma, cache_dir):
    """Cableado de compose compartido (CLI y backend). Dado choices YA resueltos
    {idx: (family, wght)} y los índices a recomponer, devuelve (svg_text, provenance,
    mask_boxes). Dueño único de la política de compose (junta ③). Lanza FontKeyError
    si el TTF falla — el orquestador decide cómo presentarlo (CLI: exit 4; backend: HTTP)."""
    # cuerpo = recompose.py:426-454 levantado sin cambios
```

**Quién resuelve `choices` NO se mueve:** el CLI lo arma con `--font` + líder + gate de empate
(EXIT 3); el backend lo armará con los clics del usuario. La función recibe la decisión ya tomada
y solo compone — la frontera fact/policy de Voronov. `main()` queda: `analyze → resolver choices
(CLI) → costura/empate (CLI, con sus exits) → compose_hybrid_svg(...) → write + preview + comandos`.

**El gate que lo protege:** byte-identidad (§5). Si el levantamiento cambia un byte del SVG, falla.

## 4. Superficie de import (las dos allowlists — el AST las cierra)

- **`recompose_core.py`** importa de `fontid`: `{download_family_weights, CACHE_DIR_DEFAULT}`;
  de `vectorize`: `{clean_binary_mask, extract_stroke_color, trace_contours}`.
- **`recompose.py`** importa de `recompose_core`: lo que `main()` use
  (`compose_hybrid_svg, seam_decision, SeamDecision, FontKeyError`, constantes); de `fontid`:
  `{analyze_regions, CACHE_DIR_DEFAULT}`; de `vectorize`: `{load_image_bgr, count_effective_colors}`.
- **Enforcement mecánico:** `test_superficie_de_imports_cerrada` se extiende para parsear el AST de
  **ambos** archivos y fallar si cualquiera excede su allowlist. La frontera la cierra el CI, no la
  prosa (el test es la fuente de verdad; si la implementación coloca un símbolo distinto, el test se
  ajusta con justificación — el procedimiento de B.1).

## 5. Testing y aceptación

- **Aceptación dura (gate de merge):** correr el CLI sobre el logo de Ale con las flags de B.1
  (`--font "mente=Nanum Myeongjo:400" --font "INTEGRATIVE PSYCHOLOGY=STIX Two Text:600"
  --contour-sigma 2`) → el SVG resultante es **byte-idéntico** al de antes del refactor → XOR 0px
  contra `logo_ale_perfecto.svg`, cero clusters ≥30px. Es no-regresión pura.
- **Reparto de los 30 tests** (junta, Vex): cada test va **donde quedó su función**. Los de
  `parse_font_arg`/`resolve_font_choices`/`seam_decision`… — ojo: `seam_decision` se mueve al core,
  así que sus tests migran al core; los de `parse_font_arg`/`resolve_font_choices` se quedan con el CLI.
- **Test nuevo:** `compose_hybrid_svg` produce el mismo `(svg_text, provenance, mask_boxes)` que el
  bloque inline para un fixture (o el del logo de Ale) — congela el levantamiento.
- **AST extendido** a `recompose_core.py` + `recompose.py` (§4).
- **Sin red en los tests de A** salvo los ya marcados `network` de B.1 (resolve_ttf descarga).

## 6. No-goals de Spec A

- **Nada de backend, nada de FastAPI, nada de JS.** Eso es B y C.
- **Cero cambio de comportamiento del CLI** — ni mensajes, ni exits, ni el SVG. Si algo del CLI
  cambia de forma observable, el refactor está mal.
- **Cero dependencias nuevas.**
- No se arregla el `.tmp` de la caché TTF (junta ②) — ese bug solo lo activa la concurrencia del
  backend; se arregla en Spec B como condición de merge. En A, single-process, es inofensivo.
- No se toca `analyze_regions` ni `fontid`/`vectorize`.

## 7. Riesgos

| riesgo | mitigación |
|---|---|
| el levantamiento de `compose_hybrid_svg` cambia un byte del SVG | gate de byte-identidad + 0px (§5) — el único gate que importa |
| un símbolo cae en la allowlist equivocada | el AST falla en CI; se ajusta con justificación |
| `seam_decision` resulta no necesitarse en el core tras especificar B | barato de revertir; va al core porque la junta ③ lo nombró hecho compartido (la costura la reporta `/analyze`) |
| romper un import circular (`recompose_core` ↔ `recompose`) | el core **no** importa de `recompose.py` — dependencia unidireccional CLI→core, verificable en el AST |
```
