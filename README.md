# vectorizer

Convierte imágenes en SVG. Dos pipelines:

- **Handwriting** (PNG/JPG escaneadas): curvas Bézier suaves, color real del trazo, limpieza de ruido y líneas de cuaderno, contornos rellenos o centerline fino.
- **Color** (`--mode color`): logos, ilustraciones y fotos (posterizadas) vía [vtracer](https://github.com/visioncortex/vtracer), con presets y flags de ajuste fino.

Extraído de [sdar.dev](https://github.com/sssamuelll/sdar.dev), donde genera los specimens de handwriting del sitio.

## Instalación

```bash
pip install -r requirements.txt
```

`opencv-contrib-python` habilita el thinning Guo-Hall (mejor calidad en modo skeleton). Si solo tienes `opencv-python`, el script cae a `scikit-image` o a un erode básico como fallback.

## Uso

```bash
# una imagen → genera palabra.svg al lado
python vectorize.py palabra.png

# salida explícita
python vectorize.py palabra.png -o salida.svg

# un directorio completo → genera ./svg_output/
python vectorize.py ./scans/ -o ./svgs/
```

## Modos

| modo | qué hace |
|---|---|
| `contour` (default) | rellena el contorno de la tinta como shapes cerrados con agujeros evenodd — máxima fidelidad, preserva el grosor del trazo |
| `skeleton` | traza la línea central como stroke fino |
| `both` | contour + skeleton encima |
| `color` | vectorización full-color con vtracer — logos, ilustraciones, fotos. Opt-in explícito; el default sigue siendo `contour` |

```bash
python vectorize.py palabra.png --mode skeleton --width 2.5
```

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
- Con `--json` la salida es solo JSON (pipe-limpio); es una **emisión draft** (su
  esquema puede cambiar cuando la Fase B de recomposición firme sus requisitos).

## Parámetros

| flag | default | qué controla |
|---|---|---|
| `--mode` | `contour` | `contour` \| `skeleton` \| `both` \| `color` |
| `--blur` | `3` | blur gaussiano previo al threshold (0 = desactivado) |
| `--rdp` | `1.0` | epsilon de simplificación Ramer-Douglas-Peucker — más alto = menos puntos |
| `--chaikin` | `2` | iteraciones de suavizado Chaikin |
| `--tension` | `0.5` | tensión Catmull-Rom de las curvas Bézier |
| `--width` | `2.0` | stroke width (solo modo skeleton) |
| `--color` | auto | fuerza un color hex (`--color "#4a9e8e"`) |
| `--no-auto-color` | — | desactiva la detección de color y usa `--color` o `#1a1a1a` |

## Pipeline

1. **Threshold** — Otsu con inversión automática según brillo del fondo, blur gaussiano opcional.
2. **Limpieza** — elimina componentes pequeños (ruido) y líneas horizontales de cuaderno por aspect ratio.
3. **Color** — extrae el color real del trazo filtrando por HSV para evitar el fondo.
4. **Contour** — `findContours` jerárquico (RETR_CCOMP): contornos exteriores + agujeros topológicos reales, renderizados con `fill-rule: evenodd`.
5. **Skeleton** — thinning Guo-Hall, corte en junctions para que cada rama sea su propio path, reconexión visual en los cruces.
6. **Curvas** — RDP → Chaikin → Catmull-Rom a Bézier cúbicas.

Las imágenes mayores a 1200px se reducen para procesar; el SVG conserva las dimensiones originales vía viewBox.
