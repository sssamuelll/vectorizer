# Vectorizador general de imágenes — Diseño

**Fecha:** 2026-06-05
**Estado:** aprobado por Samuel (diseño por secciones, conversación 2026-06-05)

## Contexto y problema

`vectorize.py` hoy asume *un solo color de tinta sobre fondo uniforme*: binariza con Otsu,
limpia ruido y líneas de cuaderno, extrae un color promedio y traza contornos rellenos o
skeleton. Funciona para handwriting pero falla con cualquier otra imagen: un logo multicolor
se aplasta a una sola máscara binaria con un solo color promedio, y la limpieza borra partes
del logo (barras horizontales, puntos pequeños).

**Objetivo:** que el proyecto vectorice cualquier imagen — logos, ilustraciones con
gradientes y fotos (estas últimas como arte posterizado, el límite físico del SVG con paths)
— sin perder la especialización en handwriting.

## Decisiones de alcance (con el usuario)

| pregunta | decisión |
|---|---|
| Alcance | Literalmente todo: logos, gradientes y fotos (posterizadas) |
| Integración | Auto-detección con flags para forzar pipeline |
| Dependencias | Libertad total — se elige vtracer (verificado: wheel `cp314-win_amd64` instala limpio en Python 3.14/Windows) |
| Prioridad | Defaults balanceados + flags para inclinar fidelidad ↔ paths limpios por imagen |

**Enfoque elegido (A):** vtracer como motor de color + router de auto-detección. El pipeline
handwriting actual queda intacto. Se descartó implementar un pipeline de color propio
(k-means + capas): mucho tuning para quedar por debajo de vtracer; y se descartó mantener
ambos (YAGNI).

## No-goals

- Reconstrucción de gradientes como `<linearGradient>` (los gradientes salen como bandas de color).
- Fotorrealismo en fotos.
- Refactor a paquete multi-archivo: todo queda en `vectorize.py` para preservar el UX de `python vectorize.py imagen.png`.
- GUI o servicio web.

## Arquitectura

```
imagen → cargar (IMREAD_UNCHANGED, alpha→blanco) → ¿--mode?
            ├─ auto (nuevo default) → detect_image_kind()
            │     ├─ "handwriting" → pipeline actual (contour)
            │     └─ "graphic"     → pipeline color (vtracer)
            ├─ contour | skeleton | both → pipeline actual
            └─ color → pipeline color
```

Dos secciones nuevas en `vectorize.py`: **detección** y **pipeline de color**. El pipeline
handwriting (threshold, limpieza, color, contour, skeleton, curvas) no se modifica, salvo el
fix de carga con alpha descrito abajo.

## Componente 1: `detect_image_kind(img) -> ("handwriting" | "graphic", razón)`

Heurística del router, en orden:

1. **Downscale** a ≤256px (lado mayor) para análisis rápido.
2. **Alpha real:** si la imagen trae canal alpha con píxeles transparentes → `graphic`.
   Los scans de handwriting no traen alpha; los logos PNG sí, constantemente.
3. **Colores efectivos:** k-means (k=8, espacio LAB, píxeles muestreados) → contar cuántos
   clusters se necesitan para cubrir el 95% de los píxeles. **≥3 colores efectivos →
   `graphic`.**
4. **Caso 2 colores** (tinta + fondo — podría ser handwriting o un logo monocromo):
   estimar **grosor medio del trazo** = área de tinta ÷ longitud del skeleton (ambos a la
   escala de análisis). Grosor medio ≤ 5px → `handwriting`; > 5px → `graphic`.
   El umbral es una constante nombrada, tunable.
5. **En caso de duda → `graphic`.** El error barato es hacia color: el pipeline handwriting
   destruye logos (su limpieza borra líneas horizontales y componentes pequeños), mientras
   que vtracer sobre handwriting da un resultado aceptable.

La decisión **siempre se imprime con su razón**:
`[AUTO] graphic (5 colores efectivos) → pipeline color`.

Las estadísticas de color calculadas aquí se reusan para elegir preset (ver Componente 2).

### Fix de alpha en el pipeline actual

Hoy `cv2.imread` (default) descarta el canal alpha: un logo PNG transparente se carga con
fondo negro basura. Se cambia a `cv2.IMREAD_UNCHANGED` + composición sobre blanco, tanto
para la detección como para el pipeline handwriting. El pipeline de color compone igual
antes de pasar los bytes a vtracer.

## Componente 2: `vectorize_color(image_path, output_path, preset, **overrides)`

Wrapper de vtracer:

1. Carga la imagen, compone alpha sobre blanco, y si el lado mayor supera `--max-dim`
   (default 1200, igual que el pipeline actual) reduce **en memoria** con INTER_AREA.
2. `cv2.imencode(".png")` → `vtracer.convert_raw_image_to_svg(bytes, img_format="png", ...)`
   → SVG string. Sin archivos temporales.
3. Post-procesa el SVG: `width`/`height` = dimensiones originales, `viewBox` = dimensiones
   de trabajo — la misma política de escala que usa el pipeline handwriting hoy.

### Presets

| preset | pensado para | parámetros vtracer |
|---|---|---|
| `logo` | colores planos, esquinas nítidas, paths editables | `filter_speckle=8`, `color_precision=6`, `layer_difference=48`, `corner_threshold=45`, `mode=spline`, `hierarchical=stacked`, `path_precision=3` |
| `drawing` | ilustraciones con sombras/gradientes suaves | `filter_speckle=4`, `color_precision=7`, `layer_difference=24`, `corner_threshold=60`, `mode=spline`, `hierarchical=stacked`, `path_precision=3` |
| `photo` | fotos → posterización fiel | `filter_speckle=4`, `color_precision=8`, `layer_difference=12`, `corner_threshold=60`, `mode=spline`, `hierarchical=stacked`, `path_precision=3` |

Sin `--preset` explícito, se elige solo reusando las estadísticas del detector:
**≤12 colores efectivos → `logo`, >12 → `photo`**. `drawing` solo se activa manualmente.
Los valores de los presets son punto de partida; se ajustan durante la implementación con
imágenes reales si hace falta.

## CLI

- `--mode auto|color|contour|skeleton|both` — **`auto` es el nuevo default.** Para imágenes
  de handwriting, auto enruta al pipeline actual → mismo resultado que hoy, cero regresión
  de comportamiento para el caso de uso original.
- Flags nuevos del pipeline de color (cada parámetro del preset tiene override individual):

| flag | mapea a |
|---|---|
| `--preset logo\|drawing\|photo` | perfil completo |
| `--colors N` | `color_precision` |
| `--speckle N` | `filter_speckle` |
| `--layer-diff N` | `layer_difference` |
| `--corner N` | `corner_threshold` |
| `--path-precision N` | `path_precision` |
| `--max-dim N` | resize previo (0 = sin resize) |

- Los flags existentes (`--blur`, `--rdp`, `--chaikin`, `--tension`, `--width`, `--color`,
  `--no-auto-color`) siguen aplicando **solo** a los modos handwriting.
- Modo directorio: igual que hoy, con routing por imagen y resumen al final.
- `requirements.txt` += `vtracer>=0.6`.
- README: documentar modos nuevos, presets y flags.

## Manejo de errores

| caso | comportamiento |
|---|---|
| vtracer no instalado | Import lazy dentro del pipeline de color. Si falta y la imagen enruta a color: mensaje claro `pip install vtracer` y exit limpio. Los modos handwriting funcionan sin él. |
| Imagen ilegible | `ValueError` actual, sin cambios. |
| vtracer falla con input raro | En modo directorio: se captura por archivo y sigue (comportamiento existente). Single-file: propaga con contexto. |
| SVG de vtracer sin atributos esperados | Se escribe tal cual (degradación, no crash). |
| Imagen en blanco | Handwriting: SVG vacío (ya es así). Color: rect del fondo. Ambos válidos. |

## Testing

pytest, fixtures sintéticas generadas con numpy/cv2 dentro de los tests — nada de binarios
commiteados. `tests/test_vectorize.py`.

| grupo | qué verifica |
|---|---|
| Router | trazos finos curvos sobre blanco → `handwriting`; logo plano 4 colores → `graphic`; gradiente → `graphic`; PNG con alpha transparente → `graphic`; logo negro sólido (2 colores, bloques gruesos) → `graphic` (el caso trampa) |
| Pipeline color | logo sintético → SVG parsea como XML válido, ≥N paths con fills distintos, root con width/height originales |
| Resize | imagen >1200px → viewBox en dims de trabajo, width/height originales |
| Overrides CLI | `--mode color` fuerza color sobre handwriting; `--mode contour` fuerza handwriting sobre un logo |
| Regresión | imagen handwriting vía `auto` produce el mismo SVG que `--mode contour` |
| Alpha | PNG transparente compone sobre blanco, no sobre negro |

## Dependencias verificadas

- `vtracer 0.6.15` — wheel `cp314-cp314-win_amd64` en PyPI, instalado y probado en la
  máquina de desarrollo (Python 3.14.4, Windows 11).
- API confirmada por inspección: `convert_image_to_svg_py(image_path, out_path, colormode,
  hierarchical, mode, filter_speckle, color_precision, layer_difference, corner_threshold,
  length_threshold, max_iterations, splice_threshold, path_precision)` y
  `convert_raw_image_to_svg(img_bytes, img_format, ...)` → SVG string.
