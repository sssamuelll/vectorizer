# vectorizer

Convierte imágenes de handwriting (PNG/JPG escaneadas) en SVG con curvas Bézier suaves. Detecta el color real del trazo, limpia ruido y líneas de cuaderno, y traza la tinta como contornos rellenos o como centerline fino.

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

```bash
python vectorize.py palabra.png --mode skeleton --width 2.5
```

## Parámetros

| flag | default | qué controla |
|---|---|---|
| `--mode` | `contour` | `contour` \| `skeleton` \| `both` |
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
