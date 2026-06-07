# Vectorizador general de imágenes — Diseño

**Fecha:** 2026-06-05
**Estado:** aprobado por Samuel (diseño por secciones, conversación 2026-06-05); revisión v2 tras junta de revisión 2026-06-05
**Versión:** v2

> **Nota de revisión.** La junta de revisión del 2026-06-05 (Serrano, Richter, Voronov,
> Halberg, Null Vale, Cassian Stride, Amina Halcyon), complementada con verificaciones
> runtime independientes, motivó esta reescritura completa (v2). El cambio estructural
> central, aprobado por Samuel, es **partir el trabajo en dos fases**: una Fase 1
> shippeable de inmediato (pipeline de color opt-in, sin cambio de contrato para
> invocaciones existentes) y una Fase 2 diferida (router de auto-detección, que se diseña
> en detalle solo después de calibrar con SVGs reales producidos por la Fase 1). El claim
> de "cero regresión" del diseño v1 era parcialmente falso —cambiar el default a `auto` es
> un cambio de contrato— y aquí se corrige de forma explícita.

## Contexto y problema

`vectorize.py` hoy asume *un solo color de tinta sobre fondo uniforme*: binariza con Otsu
(`vectorize.py:391-392`), limpia ruido y líneas de cuaderno (`clean_binary_mask`,
`vectorize.py:46-66`), extrae un color promedio (`extract_stroke_color`,
`vectorize.py:25-39`) y traza contornos rellenos o skeleton. Funciona para handwriting pero
falla con cualquier otra imagen: un logo multicolor se aplasta a una sola máscara binaria
con un solo color promedio, y la limpieza borra partes del logo (barras horizontales, puntos
pequeños — la lógica de `clean_binary_mask` elimina componentes con aspect ratio de línea
horizontal y componentes por debajo de `min_area`).

**Objetivo:** que el proyecto vectorice cualquier imagen — logos, ilustraciones con
gradientes y fotos (estas últimas como arte posterizado, el límite físico del SVG con paths)
— sin perder la especialización en handwriting.

## Decisiones de alcance (con el usuario)

| pregunta | decisión |
|---|---|
| Alcance | Literalmente todo: logos, gradientes y fotos (posterizadas) |
| Integración | Auto-detección con flags para forzar pipeline |
| Dependencias | Libertad total — se elige vtracer (verificado: wheel `cp314-cp314-win_amd64` instala limpio en Python 3.14/Windows) |
| Prioridad | Defaults balanceados + flags para inclinar fidelidad ↔ paths limpios por imagen |

**Enfoque elegido (A):** vtracer como motor de color + router de auto-detección. El pipeline
handwriting actual queda intacto. Se descartó implementar un pipeline de color propio
(k-means + capas): mucho tuning para quedar por debajo de vtracer; y se descartó mantener
ambos (YAGNI).

**Ajuste de v2 al alcance.** La integración por auto-detección sigue siendo el destino, pero
se entrega en dos fases. El default del CLI **no cambia en Fase 1** (sigue siendo `contour`).
El `auto` como default es una decisión separada, consciente y declarada, que se toma en
Fase 2 solo tras calibración con corpus real. Esto preserva el alcance acordado sin
introducir un cambio de contrato silencioso.

## No-goals

- Reconstrucción de gradientes como `<linearGradient>` (los gradientes salen como bandas de color).
- Fotorrealismo en fotos.
- Refactor a paquete multi-archivo: todo queda en `vectorize.py` para preservar el UX de
  `python vectorize.py imagen.png`. (Ver nota estructural al final de Fase 1: hay un trigger
  de revisión registrado si Fase 2 empuja el archivo mucho más allá de ~1000 líneas.)
- GUI o servicio web.
- Tratamiento **híbrido** de imágenes mixtas **dentro de `vectorize.py`**: un solo pipeline
  procesa toda la imagen. *(Reescrito 2026-06-07: el no-goal absoluto se levantó
  conscientemente para `recompose.py` — Fase B del spec de fuentes, alcance una tinta.
  `vectorize.py` por sí solo sigue sin tratamiento híbrido. Ver "Decisión cross-spec".)*

## Dependencias y hechos runtime verificados

Esta sección es **evidencia ejecutada**, no teoría. Cada punto fue observado en runtime sobre
la máquina de desarrollo y condiciona el diseño.

1. **vtracer 0.6.15**, wheel `cp314-cp314-win_amd64`, Python 3.14.4, Windows 11. Instala
   limpio.
2. **Cualquier keyword argument a las funciones de vtracer produce SIGSEGV**
   (`ACCESS_VIOLATION 0xC0000005`) que **mata el proceso entero**. Es un bug del binding
   PyO3 con Python 3.14. Verificado:
   `convert_image_to_svg_py(p, o, colormode="color")` → crash inmediato, no recuperable.
3. **La invocación 100% posicional con TODOS los parámetros funciona correctamente.**
   Verificado:
   `convert_raw_image_to_svg(img_bytes, "png", "color", "stacked", "spline", 4, 6, 16, 60, 4.0, 10, 45, 3)`
   → SVG válido. El orden posicional completo es:
   `(img_bytes, img_format, colormode, hierarchical, mode, filter_speckle, color_precision, layer_difference, corner_threshold, length_threshold, max_iterations, splice_threshold, path_precision)`.
4. **Regla de implementación no negociable:** jamás kwargs con vtracer. Se construye un
   wrapper propio con parámetros nombrados que traduce a invocación posicional completa.
   Esto es **obligación de implementación, no preferencia de estilo** — un kwarg accidental
   tumba el proceso sin excepción capturable.
5. **Imágenes diminutas** (1px, 8px, 128px sólidas) vía posicional → OK, sin crash. Un
   análisis preliminar reportó crashes con estas imágenes; quedó **refutado** — los crashes
   eran el bug de kwargs del punto 2, no el tamaño. No se incluye como riesgo.
6. **Bytes corruptos → excepción Python normal y capturable, NO segfault.** El try/except
   por archivo del modo directorio (`vectorize.py:502-506`) **sí funciona** para esta clase
   de error.
7. **El SVG de vtracer trae root**
   `<svg version="1.1" xmlns="http://www.w3.org/2000/svg" width="N" height="N">` —
   **sin `viewBox`**. El post-proceso debe **añadir `viewBox`** (dimensiones de trabajo) y
   **reescribir `width`/`height`** (dimensiones originales). Con `ElementTree` es
   **obligatorio** llamar `ET.register_namespace("", "http://www.w3.org/2000/svg")`
   **antes** de parsear, o el roundtrip contamina el árbol con prefijos `ns0:`.
8. **Explosión de paths en fotos**, medida: ruido `1000×1000` → ~28 MB de SVG, ~27k paths
   (peor caso). Mitigación: `--max-dim`. Se documenta que las fotos generan SVGs pesados.
9. **Wheels verificados solo en Windows / Python 3.14.** `requirements.txt` declara
   `vtracer>=0.6.15` con nota de plataforma.

---

# Fase 1 — Pipeline de color opt-in (shippeable de inmediato)

Fase 1 entrega un pipeline de color completo, accesible explícitamente con `--mode color`,
**sin tocar el comportamiento de ninguna invocación existente**. Es la unidad de entrega
inmediata.

## Principio de contrato: el default no cambia

- `--mode` gana `color` como opción, pero **el default del CLI sigue siendo `contour`**
  (`vectorize.py:467-469`). Toda invocación existente (`python vectorize.py palabra.png`,
  `--mode skeleton`, `--mode both`, modo directorio) produce exactamente el mismo resultado
  que hoy.
- El pipeline de color **solo** se ejecuta cuando el usuario pide `--mode color`
  explícitamente.
- No existe `--mode auto` en Fase 1. Llega en Fase 2, primero como opt-in.

## Componente: `vectorize_color(image_path, output_path, preset, **overrides)`

Wrapper de vtracer. Pasos:

1. **Carga** con la política de alpha compartida (ver más abajo): `cv2.IMREAD_UNCHANGED` +
   composición sobre blanco.
2. **Resize en memoria** con `INTER_AREA` si el lado mayor supera `--max-dim`
   (default 1200, `0` = sin resize). Este resize es **solo del pipeline de color**; el
   pipeline handwriting conserva su constante de 1200px ya presente en
   `vectorize.py:378-379`, sin cambio.
3. **`cv2.imencode(".png")`** → bytes PNG en memoria. Sin archivos temporales.
4. **Invocación posicional completa** de `vtracer.convert_raw_image_to_svg` a través del
   wrapper propio (nunca kwargs — ver hechos runtime 2-4). El wrapper expone parámetros
   nombrados internamente y los traduce al orden posicional del hecho runtime 3.
5. **Post-proceso del SVG** (ver hecho runtime 7):
   - `ET.register_namespace("", "http://www.w3.org/2000/svg")` **antes** de parsear.
   - Añadir `viewBox = "0 0 {work_w} {work_h}"` (dimensiones de trabajo).
   - Reescribir `width`/`height` a las dimensiones **originales**.
   - Es la misma política de escala que usa el pipeline handwriting en
     `vectorize.py:420-424`.

### Política de alpha compartida (un helper, tres consumidores)

Hoy `cv2.imread(str(image_path))` (`vectorize.py:372`) usa el flag por defecto, que
**descarta el canal alpha**: un logo PNG transparente se carga con fondo negro basura.

Se introduce **una sola función helper** de carga: `cv2.IMREAD_UNCHANGED` + composición
de alpha sobre blanco. Tiene **tres consumidores** y **una sola política**:

1. el pipeline handwriting (`vectorize()`),
2. el pipeline de color (`vectorize_color()`),
3. en Fase 2, la detección (`detect_image_kind()`).

> **Hallazgo de Amina Halcyon:** si la composición de alpha se implementa por separado en
> cada punto de carga, los tres divergen con el tiempo. Una sola función, una sola política.

**Esto es un cambio de comportamiento declarado, no "cero regresión".** Para PNGs de
handwriting con canal alpha, antes el alpha se descartaba (fondo negro); ahora se compone
sobre blanco. El comportamiento nuevo es correcto, pero **se declara como cambio**, no se
esconde. Para PNGs sin alpha y para JPG/BMP, el resultado es idéntico al actual.

## Presets

Los tres presets conservan los parámetros de la tabla del diseño original:

| preset | pensado para | parámetros vtracer |
|---|---|---|
| `logo` | colores planos, esquinas nítidas, paths editables | `filter_speckle=8`, `color_precision=6`, `layer_difference=48`, `corner_threshold=45`, `mode=spline`, `hierarchical=stacked`, `path_precision=3` |
| `drawing` | ilustraciones con sombras/gradientes suaves | `filter_speckle=4`, `color_precision=7`, `layer_difference=24`, `corner_threshold=60`, `mode=spline`, `hierarchical=stacked`, `path_precision=3` |
| `photo` | fotos → posterización fiel | `filter_speckle=4`, `color_precision=8`, `layer_difference=12`, `corner_threshold=60`, `mode=spline`, `hierarchical=stacked`, `path_precision=3` |

Los valores son punto de partida; se ajustan durante la implementación con imágenes reales
si hace falta.

### Selección automática de preset (cuando no se pasa `--preset`)

Sin `--preset` explícito, el preset se elige con un **análisis de colores efectivos**:

- **k-means** con `k=16`, en **espacio LAB**, sobre la imagen reducida a **≤256px** (lado
  mayor).
- **Determinismo obligatorio (verificado runtime):** semilla fija,
  `cv2.KMEANS_PP_CENTERS` y `attempts >= 3`. Sin esto, el k-means **no es determinista** —
  con `RANDOM_CENTERS` se midieron conteos de clusters distintos entre corridas sobre la
  misma imagen. La selección de preset debe ser estable: misma imagen → mismo preset
  siempre.
- Umbral: **≤12 colores efectivos → `logo`, >12 → `photo`**.
- **`drawing` solo se activa manualmente** (`--preset drawing`). Es una **decisión
  intencional**: las heurísticas de conteo de color no separan de forma fiable una
  ilustración con gradientes suaves de un logo o una foto, así que `drawing` queda como
  elección explícita del usuario y se documenta como tal.

Con `--mode color` forzado, el routing no corre (no hay router en Fase 1), pero el análisis
de colores efectivos **sí** se ejecuta cuando hace falta elegir preset.

## CLI (Fase 1)

- `--mode color` se añade a las opciones existentes (`contour|skeleton|both`). **El default
  sigue siendo `contour`.**
- Flags nuevos del pipeline de color (cada parámetro del preset tiene override individual):

| flag | mapea a |
|---|---|
| `--preset logo\|drawing\|photo` | perfil completo |
| `--colors N` | `color_precision` |
| `--speckle N` | `filter_speckle` |
| `--layer-diff N` | `layer_difference` |
| `--corner N` | `corner_threshold` |
| `--path-precision N` | `path_precision` |
| `--max-dim N` | resize previo (0 = sin resize) — **solo pipeline color**; handwriting conserva su constante de 1200px |

- Los flags existentes (`--blur`, `--rdp`, `--chaikin`, `--tension`, `--width`, `--color`,
  `--no-auto-color`, `vectorize.py:470-477`) siguen aplicando **solo** a los modos
  handwriting.

### Política de flags fuera de su modo

> **Hallazgo de Serrano.** Si el usuario pasa flags de un pipeline al modo del otro (ej.
> `--rdp` junto con `--mode color`, o `--colors` junto con `--mode contour`), **se imprime
> un warning** indicando que el flag no aplica al modo activo. **Nada se ignora en
> silencio.** El flag inerte se reporta; no altera el resultado, pero el usuario se entera.

## Import lazy de vtracer

vtracer se importa **dentro** del pipeline de color, no en el top del módulo. Si falta y la
imagen enruta a color: mensaje claro `pip install vtracer` y exit limpio. **Los modos
handwriting funcionan sin vtracer instalado** — el import lazy garantiza que el caso de uso
original no dependa de la nueva librería.

## Contrato de salida (los dos pipelines producen SVGs distintos)

> **Hallazgo combinado de Voronov, Richter y Null Vale.** Handwriting y color producen SVGs
> **estructuralmente distintos**. Esto se documenta explícitamente para que ningún consumidor
> downstream asuma una estructura única.

| aspecto | SVG handwriting (`contour`/`skeleton`/`both`) | SVG color (`color`) |
|---|---|---|
| Clases semánticas | `.ink` y `.stroke` (definidas en `<defs><style>`, `vectorize.py:426-434`) | **ninguna** clase semántica |
| Color | un color extraído del trazo, aplicado vía clase | fills por path, uno por capa de vtracer |
| Estructura de paths | grupos `<g class="ink">` / `<g class="stroke">` (`vectorize.py:436-444`) | capas apiladas (`hierarchical=stacked`) de vtracer, fill por path |
| Relleno | `fill-rule: evenodd` (agujeros topológicos) | fills planos por capa |
| Root | `width`/`height` originales + `viewBox` de trabajo | igual (tras post-proceso) |

**Regla downstream documentada:** cualquier consumidor que dependa de las clases
`.ink`/`.stroke` (selección por CSS, conteo de trazos, recoloreo) **solo debe procesar
salidas de los modos handwriting**. Las salidas de `--mode color` no llevan esas clases por
diseño.

## Limitación conocida: imágenes mixtas

> **Hallazgo de Voronov.** Una imagen mixta —por ejemplo, una nota manuscrita que incluye un
> logo a color— **no tiene tratamiento híbrido**. Un único pipeline procesa toda la imagen:
> con `--mode color`, el handwriting se traza como capas de color; con un modo handwriting,
> el logo se aplasta a una máscara binaria. Esto está **fuera de alcance de ambas fases** y
> se documenta como limitación conocida, no como bug.

**Decisión cross-spec (RESUELTA 2026-06-07).** La **Fase B** del spec de aproximación de
fuentes —recomposición de texto desde un archivo de fuente fusionado con el resto
vectorizado— **es** tratamiento híbrido de imagen mixta. La junta del 2026-06-05 lo
identificó como *"una contradicción con dos membretes"* (Voronov). El no-goal **se levanta
conscientemente** con tres acotaciones, decididas por Samuel y documentadas en el spec de
Fase B (`2026-06-07-fontid-fase-b-design.md`, §3):

1. El tratamiento híbrido vive **solo en `recompose.py`**. `vectorize.py` por sí solo sigue
   procesando toda la imagen con un único pipeline — su limitación se mantiene.
2. Alcance: **logos de una tinta**. Mixtas multicolor siguen fuera (B.x).
3. **El tercer clasificador queda nombrado**: decidir qué región se recompone y cuál se
   vectoriza es la misma pregunta que responde el router diferido de Fase 2 y que
   `classify_region` de fontid. Árbitro declarado de la costura en recompose.py:
   `classify_region` (type ∧ score ≥ 0.65). **Cuando el router de Fase 2 exista, este punto
   es el único lugar a reconciliar** — tres clasificadores respondiendo la misma pregunta
   sin árbitro divergen en silencio.

**Superficie de API declarada** (cerrada; ampliarla exige editar este spec): `recompose.py`
puede importar de `vectorize.py` **solo** `load_image_bgr`, `trace_contours`,
`extract_stroke_color`, `clean_binary_mask`. Además `vectorize.py` gana el flag
`--contour-sigma` (filtro gaussiano circular de puntos de contorno antes del RDP, default 0
= comportamiento actual sin cambio; ganador del barrido de suavizado de calibración del
2026-06-07).

## Modo directorio: resumen al final (comportamiento nuevo)

El modo directorio (`vectorize.py:491-506`) gana un **resumen al final**, con:

- conteo de imágenes procesadas **por pipeline** (handwriting vs color),
- conteo de fallos.

> Esto es **comportamiento nuevo**: hoy el modo directorio no imprime resumen agregado. Se
> declara como adición, no como "ya existía".

El try/except por archivo existente (`vectorize.py:502-506`) se conserva: un archivo que
falla no detiene el batch (válido para bytes/archivos corruptos — ver hecho runtime 6).

## Nota estructural

Todo sigue en `vectorize.py` (decisión del usuario, preserva el UX de
`python vectorize.py imagen.png`).

> **Advertencia de Richter, registrada como trigger de revisión (no como tarea actual):** si
> la Fase 2 lleva `vectorize.py` mucho más allá de **~1000 líneas**, se reevalúa extraer un
> paquete con `vectorize.py` como entry point delgado. Es un disparador de revisión futura,
> no un trabajo a hacer ahora.

---

# Fase 2 — Router de auto-detección (diferida)

Fase 2 **no es un diseño cerrado.** Es un registro de **requisitos y advertencias** para el
diseño futuro, que se hará en detalle **solo después** de calibrar contra SVGs reales
producidos por la Fase 1. Lo que sigue acota el espacio de diseño; no lo fija.

## Entrega como opt-in, default como decisión separada

- `--mode auto` llega **primero como modo opt-in**. El usuario lo pide explícitamente.
- Convertir `auto` en **default** es una **decisión separada y declarada** — un breaking
  change consciente del contrato del CLI — que se toma **solo tras calibración** con corpus
  real. No se hace por inercia.

## Router: `detect_image_kind(img) -> ("handwriting" | "graphic", razón)`

La heurística del router se diseñará en Fase 2. Requisitos y advertencias conocidos:

> **Nota cross-spec (junta 2026-06-05).** `fontid.py`
> (`docs/superpowers/specs/2026-06-05-font-identification-design.md`) introduce un **segundo
> clasificador de regiones** (tipografía↔handwriting). Este router introduce **otro**
> clasificador (handwriting↔graphic). **Dos clasificadores respondiendo la misma pregunta sin
> árbitro divergen en silencio.** Cuando este router se diseñe, ambos clasificadores **deben
> compartir política de clasificación o declarar explícitamente cuál arbitra** — qué decide
> qué, y en qué orden, ante una imagen que ambos podrían clasificar. Registrado también en el
> spec de aproximación de fuentes.

### Determinismo

Mismo régimen que la selección de preset: **semilla fija, `cv2.KMEANS_PP_CENTERS`,
`attempts >= 3`**. La decisión de routing debe ser estable entre corridas.

### Desacoplamiento de umbrales (routing ≠ configuración)

> **Hallazgo de Voronov y Richter.** La decisión de **routing** (¿qué pipeline?) y la de
> **configuración** (¿qué preset?) **no pueden compartir constantes tuneadas a ciegas**. Hoy
> `k=16` sirve a dos preguntas distintas a la vez (¿es handwriting o graphic? y ¿es logo o
> photo?). En Fase 2, **cada decisión documenta su propia constante y su justificación**, aun
> si numéricamente coinciden. Constante compartida por coincidencia, no por acoplamiento.

### Zona de duda explícita

> **Hallazgo de Richter.** El router emite una **confianza**, no solo una etiqueta. En la
> **zona incierta**, enruta a `graphic` (el error barato: el pipeline handwriting destruye
> logos; vtracer sobre handwriting da un resultado aceptable) **e imprime un warning con las
> estadísticas crudas** (conteos de cluster, grosor medido, presencia de alpha), no solo la
> decisión final. La diagnosticabilidad es requisito, no adorno.

La decisión **siempre se imprime con su razón**, por ejemplo:
`[AUTO] graphic (5 colores efectivos) → pipeline color`.

### Paso de grosor-de-trazo: en evaluación, puede no sobrevivir

El paso que estima grosor medio del trazo (área de tinta ÷ longitud del skeleton) para
desempatar el caso de 2 colores está **en evaluación** y puede **no sobrevivir** al diseño de
Fase 2. Problemas conocidos:

- **Dependencia de `cv2.ximgproc`** (hallazgo de Serrano): el fallback `erode`
  (`vectorize.py:84`) **infla** la medición de grosor — no adelgaza a centerline real. Si el
  paso se conserva, `ximgproc` pasa a ser **hard requirement del router**, no fallback.
- **Inestable sobre bloques sólidos** (hallazgo de Null Vale): el skeleton de un cuadrado
  relleno **colapsa a un punto**, lo que rompe la división área ÷ longitud.
- **Medición contaminada** (hallazgo de Voronov): usar la binarización Otsu del **propio
  pipeline handwriting** para juzgar pertenencia a handwriting mete un sesgo circular — se
  mide con la herramienta que asume la respuesta.

Si tras Fase 1 se decide conservarlo, requiere `ximgproc` como hard requirement y un manejo
explícito del caso de bloque sólido. Es legítimo que el diseño de Fase 2 lo elimine.

### Calibración de umbrales contra corpus real

> **Hallazgo de Serrano.** El umbral "≥3 colores efectivos → `graphic`" **debe calibrarse
> contra scans reales sucios**. Sombras, rayado de cuaderno y artefactos JPEG producen ≥3
> clusters en handwriting **legítimo**; un umbral fijado contra imágenes sintéticas limpias
> clasificaría mal scans reales.

**Corpus de calibración requerido antes de fijar umbrales:** scans reales de handwriting +
logos reales. La Fase 1, al producir SVGs reales por ambos pipelines, alimenta este corpus.

---

# Manejo de errores

| caso | comportamiento |
|---|---|
| **Bytes / archivos corruptos** | Lanzan **excepción Python capturable**, NO segfault (hecho runtime 6). En modo directorio: se captura **por archivo** y el batch sigue (`vectorize.py:502-506`). Single-file: propaga con contexto. |
| **kwargs a vtracer** | **SIGSEGV no capturable** (`ACCESS_VIOLATION 0xC0000005`, hecho runtime 2) que mata el proceso. Por eso la **regla posicional-only es obligación de implementación**, no estilo: el wrapper propio nunca emite kwargs hacia vtracer. |
| **Imagen ilegible** | `ValueError` (igual que hoy, `vectorize.py:374`), sin cambios. |
| **vtracer no instalado** | Import lazy dentro del pipeline de color. Si falta y la imagen enruta a color: mensaje `pip install vtracer` y exit limpio. Los modos handwriting funcionan sin él. |
| **SVG de vtracer sin atributos esperados** | Se escribe **tal cual**, PERO **con un warning impreso**. La degradación silenciosa que perdía el tamaño original era una contradicción (hallazgo de Serrano/Richter): si no se puede aplicar `width`/`height`/`viewBox`, se avisa; no se finge éxito. |
| **Imagen en blanco** | Handwriting: SVG vacío (ya es así). Color: rect del fondo. Ambos válidos. |

---

# Testing

pytest, fixtures sintéticas generadas con numpy/cv2 **dentro de los tests** — nada de
binarios commiteados. `tests/test_vectorize.py`.

## Fase 1 (a implementar con la entrega)

| grupo | qué verifica |
|---|---|
| Pipeline color | logo sintético de 4 colores → parsea como XML válido; **≥3 colores de fill distintos** detectados de forma robusta (leyendo atributo `fill` **O** `style`, sin asumir codificación — vtracer emite `fill="#XXXXXX"` por path según verificación, pero el test **no se acopla** a eso); root con `width`/`height` originales y `viewBox` presente |
| Resize | imagen >1200px → `viewBox` con dims de trabajo, `width`/`height` originales |
| Alpha | PNG transparente compone sobre **blanco**, no sobre negro |
| Errores | bytes corruptos en directorio → se captura y el batch **continúa** |
| CLI — color | `--mode color` funciona sobre cualquier imagen |
| CLI — default | el default del CLI **sigue siendo `contour`** (test explícito del default) |
| Preset determinista | misma imagen → **mismo preset** en corridas repetidas |

## Fase 2 (diferidos — listados como pendientes)

Estos tests **no se implementan en Fase 1**; quedan registrados como pendientes del router:

- Trazos finos curvos sobre blanco → `handwriting`.
- Logo plano 4 colores → `graphic`.
- Gradiente → `graphic`.
- PNG con alpha transparente → `graphic`.
- Logo negro sólido (2 colores, bloques gruesos) → `graphic` (el caso trampa de grosor).

---

# Cambios en dependencias y documentación

- `requirements.txt` actual:
  ```
  opencv-contrib-python>=4.8
  numpy>=1.24
  ```
  Se añade `vtracer>=0.6.15`, con **nota de plataforma** (wheels verificados solo en
  Windows / Python 3.14 — hecho runtime 9).
- README: documentar el modo `color`, los presets y los flags nuevos del pipeline de color;
  documentar que las fotos generan SVGs pesados (hecho runtime 8); documentar el cambio de
  comportamiento de alpha para PNGs handwriting; documentar el contrato de salida distinto
  entre pipelines.
