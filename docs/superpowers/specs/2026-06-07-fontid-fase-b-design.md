# Fase B — Recomposición (diseño)

**Fecha:** 2026-06-07
**Estado:** diseño aprobado por Samuel (secciones 1-5 + reformulación post-crítica de Voronov)
**Specs padre:**
- `2026-06-05-font-identification-design.md` (Fase B condicionada — las 3 condiciones se resuelven aquí)
- `2026-06-05-general-image-vectorizer-design.md` (no-goal de imágenes mixtas — se levanta aquí, con alcance acotado)

**Evidencia fundante:** prototipo manual completo sobre logo real
(`docs/calibration/2026-06-05-logo-libre-mente.md`, secciones "Recomposición híbrida
manual", "Ronda 2 de suavizado" y "Ronda 3: bake-off de la 'e'"; scripts en
`docs/calibration/scripts/`).

---

## 1. Qué es el producto

Tomar un logo de **una tinta** donde el texto tipográfico duele al vectorizarlo desde
píxeles, y producir un SVG híbrido: caligrafía/gráficos vectorizados desde la imagen +
texto recompuesto desde el archivo TTF de la fuente aproximada, colocado glifo a glifo
en las posiciones del original.

**El producto NO "recompone logos". Propone una recomposición y da superficies baratas
para corregirla.** La corrección es evento de primera clase, no fallo. (Ver §2.)

### Decisiones de alcance (Samuel, 2026-06-07)

| pregunta | decisión |
|---|---|
| Confirmación visual en el flujo | **Híbrido one-shot**: automático cuando el líder gana claro; se detiene en empate (Δ<0.03) |
| Qué hace "detenerse" | **Chooser interactivo en navegador** (las opciones son visuales); fallback `--font` para scripts |
| Alcance de imágenes | **Solo una tinta** (pipeline contour). Multicolor queda como B.x con su propia calibración |
| Criterio de aceptación | Una corrida sobre `logo_ale.jpeg` reproduce el equivalente de `logo_ale_perfecto.svg` (reformulado en §9 tras la crítica de Voronov) |

---

## 2. Soberanía — la regla que faltaba (hallazgo de Voronov)

El sistema tiene **tres autoridades de verdad** y ningún documento decía cuál manda:

1. **El píxel** (vectorize.py): la verdad es lo que está en la imagen.
2. **El corpus** (fontid.py): la verdad es el argmin sobre un conjunto que no contiene
   garantizadamente el objetivo — "siempre devuelve algo".
3. **El ojo** (el usuario): la verdad es lo que el ojo acepta.

**Regla de soberanía: el ojo manda.** Evidencia N=2 en el repo: el gate del spike
(condición 2 = juicio visual) y la Ronda 3 del bake-off (Cormorant ganaba en métrica
sin empate — 0.780 — y el ojo la rechazó por "barrigona"; ganó Nanum Myeongjo, inferior
en métrica de palabra).

Consecuencias arquitectónicas, todas obligatorias:

- Todo output del modo automático es un **candidato**, nunca una verdad.
- `--verify` certifica **costura** (registro geométrico, XOR), no **elección** (qué
  fuente). El render con la 'e' rechazada también pasaba el XOR. La documentación y el
  output del flag lo dicen explícitamente.
- La detención-en-empate (Δ<0.03) es "la máquina sabe que no sabe". **El caso peligroso
  es cuando la máquina no duda y se equivoca.** Puerta para ese caso: la corrida
  automática emite SIEMPRE (pare o no pare) el preview lado-a-lado + los comandos de
  corrección por región ya armados. Corregir un candidato cuesta una re-corrida con
  `--font`, no una sesión de debugging.

### Dos modos, nombrados como lo que son

- **Modo sesión** (default; humano presente): one-shot que se detiene en empate con
  chooser de navegador. No es un CLI puro — es una sesión interactiva con entrada de
  comando, y se documenta así.
- **Modo replay** (`--font` por región + `--no-browser`; scripts/CI): ejecuta
  decisiones humanas precocidas. Determinista, testeable. El CI no ejecuta el producto
  completo: ejecuta un caché de decisiones humanas previas — y eso es legítimo y
  suficiente para regresión.

---

## 3. Las tres condiciones de Fase B — resolución

**Condición 1 — Evidencia real: CUMPLIDA.** Gate del spike superado (2026-06-06),
Fase A aceptada por Samuel con el logo real (2026-06-07), y prototipo manual de
recomposición completo con verificación cuantitativa (registro 0.0px, XOR 1px global).

**Condición 2 — Contradicción cross-spec: RESUELTA AQUÍ, con alcance acotado.**
El no-goal "tratamiento híbrido de imágenes mixtas" del spec del vectorizador **se
levanta conscientemente** (edición fechada en ambos specs, ver sección "Decisión
cross-spec" de cada uno), con tres acotaciones:

1. El tratamiento híbrido vive **solo en `recompose.py`**. `vectorize.py` por sí solo
   sigue sin tratamiento híbrido — su no-goal se reescribe, no se borra.
2. Alcance: **una tinta**. Mixtas multicolor siguen fuera.
3. **El tercer clasificador se nombra** (hallazgo de Voronov: decidir qué región se
   recompone y cuál se vectoriza ES una clasificación, la misma pregunta que el router
   diferido de Fase 2 y que `classify_region`). Árbitro declarado: **`classify_region`
   de fontid es EL árbitro de la costura** en recompose.py. Regla: regiones OCR con
   clasificación `type` y score ≥ `CLASSIFY_TYPE_CUT` (0.65) → candidatas a
   recomposición; todo lo demás → tinta vectorizada. Overrides: `--skip-region N`
   (esta región se vectoriza aunque clasifique type) y `--region x0,y0,x1,y1 --text "…"`
   (región manual, heredado de fontid). Cuando el router de Fase 2 exista, esta
   declaración es el punto único a reconciliar — queda anotado en el spec del
   vectorizador.

**Condición 3 — Contrato de información: FIRMADO AQUÍ.** Fase B declara lo que
necesita (§5) y el contrato tiene **una sola fuente de forma** (hallazgo de Voronov +
ley Halcyon del repo: "una sola función, una sola política"): la dataclass
`RegionAnalysis` en fontid.py. El `--json` v1 se **serializa desde ella** — no hay dos
definiciones de campos que puedan divergir. La "emisión draft" se ratifica como
contrato v1 solo después de que esta lista entre a fontid.py; los campos nuevos que
Fase B exige y el draft no tenía: `glyph_boxes` absolutos, `scale_factor`, `tie` por
candidato, `wght` numérico ya estaba.

---

## 4. Arquitectura de módulos

```
recompose.py  (nuevo, ~400-500 líneas)
├─ orquestador CLI (one-shot; modos sesión/replay)
├─ chooser de navegador (stdlib: http.server + webbrowser; localhost efímero)
├─ compositor SVG (scratch_perfect.py productizado)
└─ verificador --verify (registro por glifo + XOR global; verifica COSTURA)

fontid.py     → expone el contrato: analyze_regions(img) -> list[RegionAnalysis]
vectorize.py  → gana --contour-sigma (filtro gaussiano circular de puntos de
                contorno antes del RDP; default 0 = comportamiento actual sin cambio;
                ganador del barrido de suavizado de calibración)
```

### Superficie de import DECLARADA (no accidental)

Hallazgo de Voronov: recompose.py convierte a fontid y vectorize en bibliotecas que no
fueron diseñadas como tales; "una API no declarada es una API que el primer consumidor
define por accidente". Respuesta: la superficie se declara aquí y en ambos specs, y es
**cerrada** — ampliar la lista exige editar los specs:

- de `fontid.py`: **solo** `analyze_regions(img) -> list[RegionAnalysis]` (función
  nueva que envuelve OCR + segmentación + clasificación + ranking + empates).
- de `vectorize.py`: **solo** `load_image_bgr`, `trace_contours` (con el nuevo
  parámetro de filtro sigma), `extract_stroke_color`, `clean_binary_mask`.

### El contrato: RegionAnalysis (única fuente de forma)

Por región:

| campo | tipo | por qué Fase B lo necesita |
|---|---|---|
| `bbox` | (x0,y0,x1,y1) absolutas | máscara de la región en la caligrafía |
| `text` | str | mapeo carácter→glifo |
| `classification` | "type"\|"handwriting" + score | árbitro de la costura |
| `glyph_boxes` | [(x0,y0,x1,y1)] absolutas | colocación glifo a glifo (el bbox crudo del crop no basta — el punto de la `i` corre el bbox; las boxes absolutas conservan baseline real) |
| `ranking` | [(family, wght, score, tie)] | elección de fuente + detección de empate |
| `scale_factor` | float | factor común del matching para volver al espacio original |

Nota sobre `opsz` (el spec padre lo pedía "si la familia lo tiene"): el pipeline de
descarga actual fija pesos discretos vía CSS2 y no captura eje óptico; el prototipo
demostró que la colocación por boxes + escala común alcanza registro 0.0px sin él.
`opsz` queda como campo **reservado** del contrato (nullable), no implementado en B.

---

## 5. Flujo de datos (one-shot completo)

```
recompose.py logo.jpeg -o logo.svg
 1. load_image_bgr → analyze_regions(img)
 2. costura: classification type ∧ score≥0.65 → recomponer; resto → vectorizar
 3. ¿empate (Δ<0.03) en el ranking de alguna región a recomponer?
    ├─ sí + modo sesión → chooser navegador (opciones renderizadas EN CONTEXTO,
    │   estilo _mente_opciones.png; radio por región; Confirmar → POST → continúa)
    ├─ sí + modo replay → error claro: "región N empatada: pasa --font 'texto=Familia:wght'"
    └─ no → líder del ranking
 4. máscara de regiones a recomponer (pad 6px) → caligrafía: Otsu + contour con
    filtro sigma (default 2 en recompose; el flag de vectorize default 0 no cambia)
 5. por región: TTF del caché o descarga → SVGPathPen → escala común (mediana de
    alturas glifo original/glifo fuente) → colocación por glifo (centro-x + fondo
    del bbox, overshoot incluido)
 6. compone SVG: grupo .ink (caligrafía) + grupo .type (texto), tinta de
    extract_stroke_color
 7. SIEMPRE emite: logo.svg + logo_preview.png (lado a lado) + comandos de
    corrección por región en stdout
 8. --verify (opcional): registro por glifo (ratio altura, Δcentro-x, Δbaseline)
    + XOR binario global con tolerancia 2px → reporta COSTURA, lo dice en el output
```

### Chooser de navegador

- Página única servida en `localhost:<puerto efímero>`; HTML autocontenido con los
  PNG de opciones embebidos (base64). Radio por región empatada, top-N candidatos
  (N=4) renderizados en contexto real con la tinta del logo.
- Confirmar → POST → el server responde "puedes cerrar", muere, y la corrida sigue.
- `webbrowser.open` inyectable (testing) y desactivable (`--no-browser`).
- Sin navegador disponible / `--no-browser` / timeout 5 min sin clic → **degrada a
  "genera opciones y sale"**: escribe los PNG de opciones + imprime el comando de
  re-corrida con `--font` armado, exit code distinto de 0 (decisión pendiente ≠ éxito).

---

## 6. CLI

```
python recompose.py logo.jpeg [-o out.svg]
  --font "texto=Familia:wght"   # decisión precocida por región (repetible) → modo replay
                                #   la clave es el texto OCR de la región; si dos regiones
                                #   comparten texto, se acepta índice: --font "2=Familia:wght"
  --no-browser                  # nunca abrir chooser; empate → genera opciones y sale
  --skip-region N               # esta región se vectoriza aunque clasifique type
  --region x0,y0,x1,y1 --text S # región manual (cuando el OCR no la ve)
  --contour-sigma F             # suavizado de caligrafía (default 2.0)
  --category / --pool / --api   # passthrough a fontid (pool de candidatas)
  --verify                      # self-check de costura post-composición
  --json                        # contrato v1 a stdout (pipe-clean, humano a stderr)
```

`sys.stdout.reconfigure(encoding="utf-8")` primera línea de main (ley del repo, consola cp1252).

---

## 7. Manejo de errores

| falla | comportamiento |
|---|---|
| OCR no detecta regiones | aviso + sugerencia de `--region`; NO vectoriza a ciegas como fallback silencioso |
| región con classify < 0.65 | se vectoriza; listada en stdout como "no recompuesta (score X)" — la costura siempre se reporta |
| descarga TTF falla | 1 reintento → siguiente del ranking con `[WARN]` a stderr |
| conteo glifos ≠ caracteres (sin espacios) | región degradada a vectorización + aviso (no adivinar alineaciones) |
| usuario cierra navegador sin elegir | timeout 5 min → degrada a "genera opciones y sale" |
| `--json` | pipe-clean: JSON v1 a stdout, todo lo humano a stderr |
| imagen multicolor (count_effective_colors > umbral de logo de una tinta) | aviso "fuera de alcance de Fase B (una tinta)" + continúa bajo responsabilidad del usuario |

---

## 8. Testing

- **Unit**: costura (scores sintéticos → decisión recompone/vectoriza), contrato
  (RegionAnalysis → JSON v1 → round-trip), colocación (asserts de registro 0.0px del
  prototipo), compositor (SVG parseable, viewBox, grupos .ink/.type, sin ns0:).
- **Chooser sin navegador real**: el server recibe `choices` y devuelve la elección;
  el test hace el POST con urllib. `webbrowser.open` inyectado como no-op.
- **Replay determinista**: misma corrida `--font` fija → SVG idéntico (normalizando
  formato de floats).
- **Degradación**: timeout/`--no-browser` con empate → PNGs + comando de re-corrida +
  exit ≠ 0.
- **Red**: descarga TTF real marcada `network` (excluida del run default), convención
  existente.

## 9. Aceptación (reformulada tras Voronov)

La versión ingenua ("una corrida reproduce el SVG manual") solo demostraría "que el
reproductor de decisiones humanas funciona". La versión honesta tiene dos partes:

1. **Replay**: `recompose.py logo_ale.jpeg --font "mente=Nanum Myeongjo:400"
   --font "INTEGRATIVE PSYCHOLOGY=STIX Two Text:600"` produce un SVG **equivalente** a
   `logo_ale_perfecto.svg`: registro 0.0px por glifo (medianas de ratio de altura,
   Δcentro-x y Δbaseline), y XOR global con tolerancia 2px **sin clusters ≥30px salvo
   los ya documentados como diferencia de ancho de glifo** (la astilla de 2px del stem
   de la 'm' de Nanum Myeongjo, calibración Ronda 3). Esto valida costura, compositor
   y contrato.
2. **Sesión**: la corrida sin `--font` sobre el mismo logo (a) se detiene en el empate
   real de "mente" (Δ=0.006 entre Cormorant Garamond y Libre Baskerville), (b) muestra
   el chooser con las opciones en contexto, (c) tras el clic continúa y termina, y
   (d) emite preview + comandos de corrección. Esto valida que **cada decisión humana
   del prototipo tiene su superficie en el producto**: fuente (chooser/`--font`),
   suavizado (`--contour-sigma`), costura (`--skip-region`/`--region`).

La aceptación final es el juicio de Samuel sobre ambas corridas, como en Fase A.

## 10. No-goals de Fase B

- Logos multicolor (texto sobre fondos de color, inpainting) → B.x, con calibración propia.
- Eje óptico `opsz` (campo reservado en el contrato, no implementado).
- Detección de la fuente "correcta" — sigue siendo aproximación sobre corpus libre
  (línea fija de corpus en cada reporte, heredada de Fase A).
- Kerning/letterspacing tipográfico propio: el espaciado SIEMPRE viene de las
  posiciones de los glifos originales, nunca de las métricas de la fuente.
- GUI más allá del chooser de un clic.

## 11. Riesgos vivos

| riesgo | mitigación |
|---|---|
| la máquina no duda y se equivoca (caso 'e') | preview + comandos de corrección SIEMPRE emitidos; documentado como propiedad del producto, no edge case |
| chooser = sesión interactiva disfrazada de CLI | nombrado en la doc; modo replay es el contrato estable para automatización |
| divergencia futura con el router de Fase 2 (tercer clasificador) | árbitro declarado en ambos specs como punto único de reconciliación |
| el contrato v1 congela campos que B.x (multicolor) no anticipa | versionado: campo `"contract": 1` en el JSON; cambios = v2, no mutación |
