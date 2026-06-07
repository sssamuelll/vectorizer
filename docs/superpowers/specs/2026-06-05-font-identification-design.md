# Aproximación de fuentes tipográficas en logos — Diseño

**Fecha:** 2026-06-05
**Versión:** v2
**Estado:** v2 — aprobado en dirección por Samuel (spike + spec honesto) tras junta de
revisión 2026-06-05 (Serrano, Richter, Voronov, Halberg, Null Vale, Cassian Stride).

> **Reframe central (Voronov / Null Vale) — gobierna todo el documento.**
> Este producto **no identifica fuentes. Aproxima.** Encuentra la alternativa más cercana
> dentro de Google Fonts. El corpus se eligió por **licencia** (familias libres, replicables
> legalmente), no por contenido: la fuente original de un logo profesional probablemente
> **no está** en Google Fonts. Un `argmin` sobre un conjunto que no contiene garantizadamente
> el objetivo **siempre devuelve algo**; el sistema no puede distinguir "encontré la fuente"
> de "encontré el vecino menos lejano de una fuente ausente". De ahí tres reglas que
> atraviesan el spec entero:
>
> 1. El título y todo el lenguaje hablan de **aproximación**, no de identificación.
> 2. Todo reporte lleva **siempre** esta línea fija:
>    `Corpus: Google Fonts. Si la fuente original es comercial, esto es la alternativa libre
>    más cercana — no una identificación.`
> 3. **Ningún score se presenta con signo `%`.** Los scores son overlaps crudos en `[0,1]`,
>    no porcentajes de certeza.

## Contexto y problema

Evidencia de calibración (`docs/calibration/2026-06-05-logo-libre-mente.md`): la tipografía
serif pequeña vectorizada desde píxeles no iguala al original ni a resolución nativa ni con
ningún tuning de suavizado — es un límite estructural del enfoque píxel→path. Cuando un logo
contiene texto compuesto en una fuente (no handwriting), recomponer el texto desde un archivo
de fuente real supera cualquier vectorización. Pero "la fuente real" rara vez es libre; lo que
este producto entrega es **la familia de Google Fonts más cercana a la observada**.

Caso motivador: logo "libre mente" — "mente" (serif estilo garalda) e "INTEGRATIVE
PSYCHOLOGY" (versalitas serif espaciadas) son las regiones donde la vectorización duele;
la caligrafía "libre" es territorio legítimo del vectorizador, no de este módulo.

## Decisiones de alcance (con el usuario)

| pregunta | decisión |
|---|---|
| Naturaleza del producto | **Aproximación**, no identificación: la alternativa libre más cercana dentro de Google Fonts. Declarado en cada reporte. |
| Output | **Por fases.** Fase A.0 = spike de validación; Fase A = producto de reporte (condicionado al gate del spike); Fase B = recomposición (condicionada, no meramente diferida). |
| Corpus | **Google Fonts** (~1.934 familias libres, replicables legalmente). Elegido por licencia, no por cobertura del espacio tipográfico. |
| Detección | **Híbrido desde el inicio**: OCR automático + flags `--region`/`--text` para forzar región/texto. |
| Local vs API | **Local por defecto; API opt-in explícito** (flag `--api`). La sola presencia de `ANTHROPIC_API_KEY` no activa nada. |

**Enfoque elegido (A): embudo de etapas** — OCR local → filtro por metadata → matching por
render. Se descartó el índice pre-computado de features (B: overkill para CLI personal,
YAGNI) y el API-céntrico (C: viola "local primero" y delega la decisión a un tercero).

## Hechos runtime verificados (evidencia ejecutada por Halberg, 2026-06-05)

Esta sección es **evidencia ejecutada en la máquina de desarrollo**, no teoría. Cada punto
condiciona el diseño, y varios **invierten** o **refutan** afirmaciones del borrador v1.

1. **winocr instala y corre en Python 3.14.4 / Windows 11**, PERO `lang='en'` falla con
   `AssertionError` — esta máquina **solo tiene packs OCR `es-ES` / `es-MX`**. Con
   `lang='es'`: OCR en **0.05s**, texto correcto, bounding boxes por palabra y por línea.
   → **Jamás hardcodear el idioma del OCR.**
2. El OCR **no emite región para la palabra caligráfica "libre"** — la descarta en silencio.
   → El flujo automático no puede prometer cobertura de zonas handwriting.
3. La **API CSS2 de Google Fonts con el User-Agent por defecto de `urllib`** entrega
   **TTF directo** (290 KB, 0.76s, Pillow lo abre sin problema). El User-Agent legacy de
   IE11 entrega **WOFF** (peor). **El "truco UA legacy" del v1 estaba invertido** y se
   elimina del diseño.
4. La metadata `fonts.google.com/metadata/fonts` trae **1.934 familias**, JSON limpio
   **sin prefijo anti-hijacking** (se parsea directo), con categorías en **Title Case**.
   Distribución: `Sans Serif` 715, `Display` 465, `Handwriting` 356, `Serif` 348,
   `Monospace` 50.
5. La segmentación por **componentes conexos fragmenta letras con punto**: "integrative"
   (11 letras) → **13 componentes**. "mente" la esquiva por suerte (no tiene puntos).
   → La fusión vertical es **requisito de Fase A**, no del spike.
6. **Matching end-to-end sobre el crop real de "mente":** Cormorant **0.707**,
   Georgia **0.680**, Times **0.671**, Arial **0.489**. La métrica separa serif-de-sans con
   holgura (margen **0.218**) pero serif-vs-serif vive en el ruido (margen **0.027**).
   → De ahí el **umbral de empate 0.03** y el **reporte de dos niveles**.
7. **winocr usa `asyncio.run` internamente** → **no es thread-safe**. El OCR corre
   **secuencial en el hilo principal**, obligatoriamente.

---

# Fase A.0 — Spike (ejecutable de inmediato, ~4 horas)

Marco de Cassian Stride: el spike **no es un mini-producto**, es un experimento con una
pregunta y un gate.

**La pregunta que responde:** ¿el matching glifo-a-glifo rankea la fuente correcta — el
cluster garalda — **arriba** para "mente" e "INTEGRATIVE PSYCHOLOGY" del logo real?

Si la respuesta es no, la Fase A **no se construye** y el aprendizaje se documenta. El spike
existe para **falsar**, no para confirmar.

## Alcance del spike (lo que SÍ y lo que NO)

CLI mínimo, nada más:

```bash
python fontid.py logo.png --region x0,y0,x1,y1 --text "mente"
python fontid.py logo.png --region 270,755,1230,855 --text "INTEGRATIVE PSYCHOLOGY" \
                          --region 450,600,1050,770 --text "mente"
```

- `--region` y `--text` son **pares posicionales, repetibles**. Si los conteos difieren
  (N regiones, M textos, N≠M) → **error claro** antes de procesar.
- **Sin OCR, sin clasificación, sin API, sin `--json`, sin `--preview`.** Todo eso es Fase A.

## Pool fijo del spike (hardcodeado)

~20 familias **serif garaldas / transicionales** de Google Fonts, elegidas por popularidad,
hardcodeadas en el script (sin metadata, sin filtro — el spike no negocia el espacio de
búsqueda, lo fija a mano):

```
Cormorant Garamond, EB Garamond, Cormorant SC, Crimson Pro, Crimson Text,
Sorts Mill Goudy, Gilda Display, Playfair Display, Lora, PT Serif,
Libre Baskerville, Source Serif 4, Noto Serif Display, Cardo, Spectral,
Domine, Frank Ruhl Libre, Marcellus, Cinzel, Old Standard TT
```

**Más 4 controles negativos** (sans/display, etiquetados como tales en el código): `Roboto`,
`Montserrat`, `Oswald`, `Pacifico`. Sin ellos, la condición 1 del gate ("cluster serif
separado del resto") sería **inmedible** — un pool 100% serif no tiene "resto" del cual
separarse. Los controles dan la línea base del margen serif-vs-sans (~0.2, hecho runtime 6).

## Descarga y validación de TTF (spike)

- **`urllib` con el User-Agent por defecto** contra la API CSS2 de Google (hecho runtime 3:
  entrega TTF directo). **No** se usa el UA legacy de IE11 — entregaba WOFF, peor. El
  "truco" del v1 estaba invertido y queda eliminado.
- **Validación ANTES de cachear:** (1) magic bytes del archivo, (2) apertura efectiva con
  `PIL.ImageFont.truetype`. Si no abre → se descarta, **no** se cachea.
- **Escritura atómica:** se descarga a un archivo temporal y se hace `rename` solo tras
  validar. Nunca queda un TTF a medias en la caché.
- Carpeta `./ttf_cache/` simple, **sin TTL** — el TTL formal es de Fase A; en el spike la
  caché es desechable.

## Segmentación del spike (límites declarados)

- **Componentes conexos ordenados por x, SIN fusión vertical.** Es lo más simple que
  responde la pregunta del spike.
- **Límite declarado del spike:** falla con minúsculas de punto (`i`, `j`) y con acentos —
  los parte en dos componentes (hecho runtime 5). Las palabras del caso motivador ("mente",
  "INTEGRATIVE PSYCHOLOGY") **no los tienen**, así que el spike las procesa correctamente.
- **La fusión vertical es requisito de Fase A**, no del spike (hecho runtime 5:
  "integrative" → 13 componentes sin fusión).

## Métrica del spike (enriquecida)

Esta métrica responde directamente al hallazgo de **Richter / Voronov** — *la normalización
por glifo borra las dimensiones discriminantes* — confirmado por las mediciones de Halberg
(hecho runtime 6, donde serif-vs-serif quedó dentro del ruido):

- **Escala con UN factor común** para todos los glifos del render, anclado a la **altura
  mediana de los glifos del crop**. **No** se escala glifo por glifo. Así las proporciones
  relativas (x-height vs caps, contraste de pesos) **sobreviven**, y los desajustes de tamaño
  **penalizan** el IoU en lugar de borrarse.
- **Alineación por centroide, por glifo.** Las posiciones horizontales **no** son confiables
  por el tracking custom de los logos — eso sí se normaliza, y se documenta el porqué: el
  espaciado del logo es decisión de diseño del logo, no de la fuente.
- **Score por glifo = IoU** de las dos máscaras binarias.
- **Score de candidata = media truncada:**
  - región con **≥4 glifos** → se descarta el **peor** glifo (robustez contra un glifo mal
    segmentado);
  - región con **2–3 glifos** → media simple (descartar uno borraría demasiada señal);
  - región con **<2 glifos** → se marca **"insuficiente para matching"** y no se rankea
    (hallazgo Serrano: monogramas y logos de una sola letra).

## Contrato del número (BLOCKER 1 de Serrano)

- El score se reporta como **"overlap" crudo en `[0,1]` con 3 decimales** + el **delta al
  siguiente candidato**. Nunca como porcentaje, nunca con `%`.
- **Umbral de empate: `delta < 0.03`** — medido por Halberg (hecho runtime 6: el margen real
  serif-vs-serif fue **0.027**). Los candidatos dentro de `0.03` del líder se marcan
  **"EMPATE — indistinguibles a esta resolución"**.
- **Reporte de dos niveles:**
  - el **cluster** es confiable: ej. *"garalda serif, claramente separada de sans:
    0.707 vs 0.489"*;
  - el **orden interno del cluster no lo es**, y el reporte lo dice explícitamente.

## Binarización del crop (spike)

- **Otsu directo** sobre el crop, **sin `clean_binary_mask`** de `vectorize.py`
  (`vectorize.py:80-100`). Esa función **destruye puntos, serifas y barras finas por diseño**
  — descarta componentes por `min_area` y por aspect de línea horizontal; es limpieza de
  **cuadernos**. Usarla aquí sería aplicar la herramienta exactamente opuesta a la necesaria.
- **Corrección del v1:** la afirmación de que *"la maquinaria de segmentación ya existe en
  `vectorize.py`"* es **falsa** (verificado por Serrano y Richter contra el archivo real).
  La única segmentación por componentes conexos del módulo vive **acoplada** dentro de
  `trace_skeleton` (`vectorize.py:178+`) y `clean_binary_mask`, ninguna reutilizable. **La
  segmentación de `fontid` es código nuevo.**
- **Lo único que se importa de `vectorize.py` es `load_image_bgr`** (`vectorize.py:33-52`) —
  misma política de alpha (composición sobre blanco), nada más.

## Test del spike

Un test, `tests/test_fontid.py`:

- mini-pool de **3 fuentes del sistema** (Georgia, Times New Roman, Arial — siempre
  presentes en Windows),
- un texto **renderizado con Georgia**,
- aserción: **Georgia gana el ranking**.

Es un test de cordura del mecanismo, no del caso motivador (ver el límite de fixtures en
Fase A → Testing).

## Gate de salida del spike

Sobre el **logo real**, el spike pasa solo si se cumplen las dos condiciones:

1. **El cluster serif queda separado del resto** (el margen serif-vs-sans del orden de 0.2,
   no el margen serif-vs-serif del orden de 0.03).
2. **Juicio visual de Samuel** sobre la top-1 recompuesta a mano.

Si el gate **falla**, la **Fase A no se construye** y el aprendizaje se documenta en
`docs/calibration/`. El gate es la condición de existencia de todo lo que sigue.

---

# Fase A — Producto de reporte (condicionada al gate del spike)

Todo lo del borrador v1 **pero corregido con el roast y los hechos runtime**. Nada de esta
fase se implementa hasta que el spike pase su gate.

## Arquitectura

**Módulo nuevo `fontid.py`**, hermano de `vectorize.py` en el mismo repo. Respeta el trigger
estructural de ~1000 líneas registrado en el spec del vectorizador; esta feature **no** entra
en `vectorize.py`. Lo único compartido es `load_image_bgr`.

CLI:

```bash
python fontid.py logo.png                                          # automático total
python fontid.py logo.png --region 270,755,1230,855 --text "INTEGRATIVE PSYCHOLOGY"
python fontid.py logo.png --json                                   # emisión draft (ver Fase B)
python fontid.py logo.png --preview                                # + tira PNG comparativa
python fontid.py logo.png --api                                    # nominación API opt-in
python fontid.py logo.png --pool 60 --category serif
```

## OCR (negociación de idioma — nunca hardcodear)

- El idioma del OCR se **negocia en runtime** vía
  `OcrEngine.available_recognizer_languages` — **jamás** se hardcodea `'en'` (hecho
  runtime 1: esta máquina solo tiene `es-ES` / `es-MX`; con `lang='en'` el OCR lanza
  `AssertionError`; con `lang='es'` corrió en 0.05s y leyó "mente" e "INTEGRATIVE
  PSYCHOLOGY" con bboxes correctas).
- Se elige el **primer recognizer de script latino disponible**. Si no hay ninguno → error
  con la instrucción de instalación de Windows (`Add-WindowsCapability`).
- **Limitación documentada:** el OCR **puede no emitir región** para texto caligráfico
  (hecho runtime 2: "libre" no aparece en el resultado). El flujo automático **solo reporta
  las regiones detectadas**, acompañadas de un **aviso fijo** de que las zonas handwriting
  pueden no listarse; `--region`/`--text` cubre el resto (de ahí el híbrido).
- **Windows-only declarado:** `winocr` depende de `winrt` / `Windows.Media.Ocr`, que **no
  existe fuera de Windows**. En un SO no-Windows el módulo emite un error claro (ver tabla de
  errores).
- **OCR secuencial obligatorio:** `winocr` usa `asyncio.run` internamente → **no es
  thread-safe** (hecho runtime 7). El OCR corre **secuencial en el hilo principal**. Esta es
  una **restricción de invocación documentada**, no un detalle de implementación.

## Clasificación de regiones (reframed por Voronov)

> **No es una tricotomía ontológica.** Es **un score escalar** tipografía↔handwriting con
> **dos cortes** que definen una **banda de incertidumbre declarada**. `uncertain` es estado
> **del clasificador**, no del mundo — y el spec lo dice explícitamente.

Señales:

1. **Consistencia de baseline** (regresión sobre centros de palabras → residuo bajo =
   tipografía).
2. **Variación de altura** de glifos.
3. **Repetición de formas.** Esta señal **solo aporta cuando hay glifos repetidos**. En
   palabras cortas sin repetición — **la mayoría de los logos** — la clasificación usa **solo**
   baseline y altura, y el reporte **declara esa limitación**.

- Resultado por región: un score escalar con su banda. `type` pasa al matching;
  `handwriting` se reporta como *"se vectoriza, no se aproxima"*; la banda incierta se reporta
  con la sugerencia de `--region`/`--text`.
- **El reporte de región imprime las estadísticas crudas** (residuo de baseline, variación de
  altura), **no** un "0.91" desnudo sin calibración. Un número calibrado solo es honesto si
  hubo calibración; aquí no la hay todavía, así que se muestran las señales.

> **Aviso cross-spec (junta 2026-06-05).** `fontid.py` introduce un **segundo clasificador**
> de regiones (tipografía↔handwriting). El router del vectorizador (Fase 2 del spec hermano)
> introduce **otro** clasificador (handwriting↔graphic). **Dos clasificadores respondiendo la
> misma pregunta sin árbitro divergen en silencio.** Cuando el router se diseñe, ambos
> clasificadores **deben compartir política de clasificación o declarar explícitamente cuál
> arbitra.** Registrado también en el spec del vectorizador.

## Filtro de candidatas (metadata, local)

Features **robustas** del crop binarizado (deliberadamente **no** se intenta detectar "serif"
desde píxeles — frágil):

- **caps-only** (del texto OCR'd) → prioriza familias con small caps / versalitas;
- **peso aproximado** (densidad de tinta / área de glifo) → acota el rango `wght`;
- **slant** (ángulo medio de strokes verticales) → italic sí/no.

Filtran la metadata de Google Fonts. **Las categorías reales son Title Case** (hecho
runtime 4): `"Serif"`, `"Sans Serif"`, `"Display"`, `"Handwriting"`, `"Monospace"`. La
metadata trae **1.934 familias**, JSON limpio **sin prefijo anti-hijacking** (se parsea
directo). El input de `--category` se **normaliza** a Title Case antes de comparar.

- **Pool default 60** (no 150). **Presupuesto declarado:** descarga paralela (8 conexiones,
  escritura atómica) ≈ **45–60s en frío**; corridas siguientes desde caché. Flags:
  `--pool N`, `--category serif`.

## API opt-in explícito (hallazgo de privacidad de Serrano)

- **Flag `--api` requerido.** La sola presencia de `ANTHROPIC_API_KEY` **no activa nada**.
  Razón: los logos pueden ser **material confidencial de clientes**; enviar el crop a un
  tercero es una **decisión explícita** del usuario, nunca un default.
- **Máximo 1 call por invocación.**
- La API **solo nomina** candidatas; toda verificación es **local y determinista**.
- **Hallazgo de Null Vale, reconocido:** nominar dentro de un pool acotado **ES decidir el
  espacio de búsqueda**. Por eso el **default es sin API** y el pool por popularidad, y el
  reporte **marca qué candidatas entraron por nominación API** — para que el sesgo del
  nominador sea visible, no implícito.

## Coordenadas (invariante declarado)

**Todo bbox del JSON y del reporte va en coordenadas absolutas de la imagen original.** Los
offsets de los crops se convierten **siempre** de vuelta al espacio original. No hay
coordenadas relativas al crop en ninguna salida.

## Matching glifo-a-glifo (local, determinista)

Mismo principio y métrica que el spike (factor de escala **común**, alineación por centroide
por glifo, IoU por glifo, media truncada según conteo de glifos, umbral de empate 0.03,
reporte de dos niveles), **más** lo que el spike dejó como requisito de esta fase:

1. **Descarga TTF** vía API CSS2 con UA por defecto de `urllib` (hecho runtime 3), a caché,
   con validación previa (magic bytes + `ImageFont.truetype`) y escritura atómica.
2. **Segmentación con fusión vertical:** componentes conexos ordenados por x **+ fusión
   vertical** de componentes solapados en x (puntos de `i`/`j`, acentos). Hecho runtime 5:
   sin fusión, "integrative" da 13 componentes para 11 letras; con fusión, 11.
3. **Render por carácter** con Pillow, escala con el factor común, alineación por centroide.
4. **Pesos:** si la familia es variable o multi-peso, se prueba `wght` 300–700 y se conserva
   el mejor; el `wght` elegido se registra (lo necesita Fase B).
5. **Ranking → top-5** con overlaps crudos, deltas y marca de EMPATE donde aplique.

## Reporte

Salida humana (default). **Nota:** los números son overlaps crudos en `[0,1]`, **no
porcentajes**, y el bloque cierra con la línea fija de corpus.

```
Corpus: Google Fonts. Si la fuente original es comercial, esto es la
alternativa libre más cercana — no una identificación.

[REGIÓN 1] "mente" — tipografía (baseline res=2.1px, var. altura=0.04)
  cluster: garalda serif, separada de sans (0.707 vs 0.489, margen 0.218) ✓ confiable
  orden interno del cluster: NO confiable (márgenes < umbral de empate)
  1. Cormorant Garamond   overlap 0.707   (Δ 0.027 al #2 → EMPATE)
  2. Lora                 overlap 0.680   (Δ 0.009 al #3 → EMPATE)
  3. EB Garamond          overlap 0.671
  ...
[REGIÓN 2] "libre" — handwriting → se vectoriza, no se aproxima
[REGIÓN 3] "INTEGRATIVE PSYCHOLOGY" — tipografía (caps-only)
  cluster: versalitas serif, separada de sans ✓ confiable
  1. Cormorant SC         overlap 0.74    [API]   ← entró por nominación API
  ...

Aviso: zonas con texto caligráfico pueden no listarse arriba (el OCR no
siempre emite región para handwriting). Usa --region/--text para forzarlas.
```

- `--json`: estructura máquina (regiones, bboxes absolutos, texto, score escalar de
  clasificación + estadísticas crudas, candidatas + overlaps + deltas + marca de empate +
  marca `[API]`, rutas de TTF cacheados, `wght` elegido, factor de escala del crop).
  **Hasta que Fase B firme sus requisitos, esto es una "emisión draft", no un contrato**
  (ver Fase B).
- `--preview`: PNG, tira comparativa por región (crop original vs top-3 renders) para juicio
  visual humano.

## Caché

`~/.cache/vectorizer-fonts/`:

- `metadata.json` de Google Fonts (endpoint público `fonts.google.com/metadata/fonts`,
  sin key), con **TTL semanal**;
- TTFs descargados on-demand (una vez por familia), **validados antes de persistir**
  (magic bytes + `ImageFont.truetype`), con **escritura atómica** (temp + rename). Un TTF
  corrupto descargado **se descarta**, no se cachea.

## Errores

| caso | comportamiento |
|---|---|
| `winocr` no instalado | mensaje claro `pip install winocr` + exit limpio |
| `winocr` instalado sin language pack | error con la instrucción de Windows (`Add-WindowsCapability -Online -Name Language.OCR~~~es-ES~0.0.1.0` o equivalente del script latino disponible) — hecho runtime 1 |
| `winocr` falla en runtime | fallback **documentado** a `--region` + `--text` (matching manual de la región) |
| SO no-Windows | error claro: el módulo es Windows-only (`winocr`/`winrt` no existe fuera de Windows) |
| red parcial al descargar fuentes | matching **solo contra caché** + warning con **conteo de candidatas omitidas** |
| TTF corrupto descargado | se **descarta** (validación previa), **no** se cachea; se reporta y se sigue con las demás candidatas |
| región forzada sin `--text` | error claro: `--region` exige `--text` acompañante |
| región con <2 glifos | se marca **"insuficiente para matching"** y no se rankea (monogramas) |
| imagen ilegible | `ValueError` (misma política que `vectorize.py:565`) |

## Testing

pytest, `tests/test_fontid.py`. Fixtures sintéticas renderizadas in-test con fuentes del
sistema Windows (Georgia, Times New Roman, Arial — siempre presentes) para no depender de red
en el camino feliz, **más** los grupos que el roast exigió:

| grupo | qué verifica |
|---|---|
| Clasificación | región renderizada con fuente → score lado-tipografía; trazos curvos irregulares sintéticos → score lado-handwriting |
| Segmentación — sin puntos | "mente" renderizada → N componentes = N caracteres |
| **Fusión vertical** | **"integrative" renderizada → 11 glifos tras fusión** (sin fusión serían 13, hecho runtime 5) |
| Matching | mini-pool local de 3 TTFs del sistema → la fuente correcta gana el ranking |
| **Empate declarado** | dos fuentes casi idénticas → el reporte marca **EMPATE** (delta < 0.03) |
| Contrato del número | el score sale en `[0,1]` con 3 decimales y delta; **nunca** con `%` |
| Coordenadas | bbox de un crop con offset → reportado en coordenadas **absolutas** |
| CLI | `--region`+`--text` fuerzan; conteos N≠M → error; `--json` parsea; default = reporte humano |
| Caché | segunda corrida no re-descarga metadata ni TTFs; TTF corrupto no se persiste |
| **Red — garalda real** (`@pytest.mark.network`, skip por default) | descarga real de metadata GF + **una garalda real de GF** y verifica que rankea en el cluster serif |

> **Hallazgo de Null Vale, atendido.** Las fixtures de fuentes del **sistema** (Georgia,
> Times, Arial) **no cubren la clase del caso motivador** — son fuentes que el matcher ya
> separa con holgura, y un test que solo use esas fixtures **confirma en vez de falsar**. Por
> eso el test `@pytest.mark.network` con una **garalda real de Google Fonts** es obligatorio:
> es el único que pone a prueba la zona de ruido (serif-vs-serif) donde el producto realmente
> vive.

---

# Fase B — Recomposición (condicionada, NO meramente diferida)

Recomposición: tomar el match ganador, extraer outlines de glifos del TTF
(`fontTools` → SVG paths), posicionarlos según las bboxes replicando el tracking medido, y
fusionar con la salida vectorizada del resto de la imagen (vía `vectorize.py`) en un SVG
híbrido.

> **Esto no es "diferido y ya".** Es **condicionado a tres cosas explícitas** antes de
> siquiera diseñarse. Diferir sin condiciones esconde la deuda; aquí se nombra.

**Condición 1 — Evidencia real.** Gate del spike superado **+** Fase A funcionando con
evidencia real (no sintética).

**Condición 2 — Resolución de la contradicción cross-spec.** El spec del vectorizador declara
las **imágenes mixtas fuera de alcance**, y la recomposición **ES** tratamiento híbrido de
imagen mixta (texto recompuesto desde fuente + resto vectorizado en el mismo SVG). Es,
en palabras de Voronov, *"una contradicción con dos membretes"*. **Levantar ese no-goal será
una decisión consciente y documentada en AMBOS specs** — no un hecho consumado por la puerta
de atrás. Mientras no se levante explícitamente, Fase B no se diseña.

**Condición 3 — El contrato de información se define ANTES de congelar el JSON de Fase A.**

> **Hallazgo de Richter:** un contrato necesita **dos partes**. Si Fase A congela su JSON sin
> que Fase B haya declarado qué necesita, el "contrato" lo firma una sola parte y a Fase B le
> faltará información que ya no se puede reconstruir.

Como mínimo, Fase B necesitará **por glifo**:

- **baseline y origen tipográfico** por glifo — no solo bboxes: el **punto de la `i`** corre
  el bbox respecto a la baseline real, así que el bbox crudo no basta;
- el **valor numérico de `wght`** elegido en el matching;
- el **eje óptico `opsz`** si la familia lo tiene — **crítico en garaldas** (Cormorant /
  EB Garamond cambian de forma con el tamaño óptico);
- el **factor de escala global del crop** — la transformación que el matching **conserva**
  gracias al factor común (no por glifo), y que Fase B necesita para volver al espacio
  original.

**Hasta que Fase B firme sus requisitos**, el `--json` de Fase A se denomina **"emisión
draft"**, no contrato. El nombre es deliberado: avisa a cualquier consumidor de que la
estructura aún puede cambiar cuando Fase B firme.

## Riesgos conocidos (resueltos o vivos)

| riesgo (v1) | estado en v2 |
|---|---|
| `winocr` en Python 3.14 no verificado | **Resuelto** (hecho runtime 1): instala y corre; el riesgo real era el idioma hardcodeado, ya corregido. |
| Truco del User-Agent legacy para TTF | **Invertido y eliminado** (hecho runtime 3): el UA por defecto entrega TTF; el legacy entregaba WOFF. |
| Segmentación parte glifos con punto | **Conocido y planificado** (hecho runtime 5): fusión vertical es requisito de Fase A, con su propio test. |
| IoU sensible a anti-aliasing / binarización | **Vivo, acotado.** Por eso el reporte de dos niveles: el cluster es confiable, el orden interno no. El umbral de empate 0.03 (hecho runtime 6) absorbe el ruido en vez de fingir precisión. |
| Argmin sobre corpus que no contiene el objetivo | **Vivo por diseño** — es la naturaleza del producto, no un bug. Mitigado con el reframe: la línea fija de corpus en cada reporte y el lenguaje de "aproximación". |
