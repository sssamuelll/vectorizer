# Calibración: logo "libre mente" (JPEG, tinta única sobre fondo claro)

**Fecha:** 2026-06-05 · **Input:** JPEG 1507×1044, caligrafía verde salvia (#87b1a4) sobre
fondo casi blanco — visualmente 2 colores. Primer caso real del corpus de calibración de
Fase 2 (spec: "Calibración de umbrales contra corpus real").

## Corridas

| corrida | resultado | KB | paths | fills |
|---|---|---|---|---|
| `--mode color` (preset auto → logo, 4 colores efectivos) | fiel, pero ruidoso | 49.2 | 50 | **46** |
| `--mode color --preset logo --colors 4` | casi igual | 43.7 | 45 | 40 |
| `--mode color --preset logo --layer-diff 128` | casi igual | 39.1 | 39 | 37 |
| `--mode contour` (pipeline handwriting) | **el más limpio** | 92.9 | 33 | **1** |

## Hallazgos

1. **El ruido JPEG se convierte en capas.** Un logo visualmente bicolor produce 46 fills
   distintos en vtracer: cada letra/segmento sale como shape espacialmente separado con su
   color medio propio (verdes #8AB2A5→#AAC7BE, blancos #E4F0ED→#FDFEFE). Visualmente se
   notan parches pálidos sutiles dentro de los counters de la caligrafía (halos del JPEG
   vectorizados como capas casi-blancas sobre el verde).
2. **`--colors` y `--layer-diff` apenas reducen fills en shapes espacialmente separados.**
   46→40 y 46→37 respectivamente. `layer_difference` gobierna la granularidad de capas por
   gradiente, no fusiona paths separados con colores casi idénticos. Para colapsar un logo
   bicolor ruidoso a 2 fills haría falta cuantización previa de la imagen (no expuesta hoy)
   o post-proceso del SVG.
3. **Para tinta única, el pipeline handwriting gana con claridad.** `--mode contour`: 1 solo
   fill con el color real extraído (#87b1a4), counters limpios sin parches, tipografía
   pequeña mejor definida. Más pesado en KB (sampling denso + pretty-print), pero
   estructuralmente lo que un diseñador quiere de un logo monocolor.
4. **Evidencia para el router de Fase 2:** la heurística "2 colores efectivos + trazo fino →
   handwriting" habría enrutado este caso **correctamente** a contour. Nota: el conteo de
   colores efectivos dio **4** (no 2) por el ruido JPEG — confirma el hallazgo de Serrano de
   que el umbral "≥3 → graphic" malclasificaría inputs reales sucios; el umbral de routing
   necesita calibrarse con el conteo *post-ruido*, no el teórico.
5. Menor, pre-existente: `np.cross` emite DeprecationWarning (NumPy 2.0) en `rdp_simplify`
   (`vectorize.py:256`) al correr contour. Limpieza barata pendiente.

## Sweep de suavizado (contour, 5 variantes juzgadas visualmente)

| variante | flags | small text | caligrafía | suavidad | KB |
|---|---|---|---|---|---|
| A | defaults (blur 3, rdp 1.0, chaikin 2) | 4 | 8 | 6 | 92.9 |
| **B** | `--blur 1 --rdp 0.4 --chaikin 3` | **6** | **9** | **7** | 342 |
| C | `--blur 3 --rdp 0.5 --chaikin 3 --tension 0.6` | 6 | 8 | 7 | 339.8 |
| D | `--blur 5 --rdp 0.8 --chaikin 4` | 3 | 9 | 7 | 506.8 |
| E | `--blur 0 --rdp 0.3 --chaikin 3` | 6 | 8 | 6.5 | 345.8 |

**Ganadora: B** (`--blur 1 --rdp 0.4 --chaikin 3`) — mejor caligrafía sin sacrificar el
texto pequeño más de lo inevitable. Hallazgo unánime de las 5 evaluaciones: **ninguna
combinación de knobs arregla "INTEGRATIVE PSYCHOLOGY"** — los stems finos de las versalitas
se erosionan en todas las variantes.

## Causa raíz del texto pequeño: la resolución, no el suavizado

Probe a resolución nativa (1507px, saltando el resize hardcodeado a 1200px del pipeline
handwriting, mismos parámetros que B): el texto pequeño **recupera el peso de trazo y las
serifas casi por completo**. Comparación visual directa original/1200px/nativo lo confirma.

**Acción candidata (Fase 1.x):** extender `--max-dim` a los modos handwriting (default 1200
→ cero regresión; opt-in a resolución nativa con `--max-dim 0`). Hoy `--max-dim` es solo
del pipeline color.

**Límite estructural:** aún a resolución nativa, la tipografía serif pequeña vectorizada
desde píxeles no iguala al original — evidencia directa para la feature de identificación
de fuentes (en diseño): texto tipográfico se replica mejor desde el archivo de fuente que
desde píxeles.

## Implicaciones acumuladas para Fase 2

- El router debe tolerar 3-5 colores efectivos en imágenes que son conceptualmente
  bicolores (JPEG sucio) antes de declarar `graphic`.
- El caso "logo de tinta única" refuerza que el paso de grosor-de-trazo (o un sustituto)
  importa: este logo tiene trazos finos caligráficos → handwriting fue lo correcto, pero
  un logo monocolor de bloques gruesos seguiría necesitando `graphic`.

## Spike A.0 — resultado del gate (2026-06-05)

```
Corpus: Google Fonts. Si la fuente original es comercial, esto es la
alternativa libre más cercana — no una identificación.

[REGIÓN 1] "mente"
  separación del cluster vs controles: 0.270 (OK — gate condición 1)
  1. Libre Baskerville      overlap 0.747
  2. Cormorant Garamond     overlap 0.737   Δ 0.010  → EMPATE con el líder
  3. EB Garamond            overlap 0.683   Δ 0.054
  4. Crimson Text           overlap 0.668   Δ 0.014
  5. Lora                   overlap 0.663   Δ 0.005
  [control] Roboto         overlap 0.477
  [control] Montserrat     overlap 0.434
  [control] Oswald         overlap 0.368
  [control] Pacifico       overlap 0.309

[REGIÓN 2] "INTEGRATIVE PSYCHOLOGY"
  separación del cluster vs controles: 0.188 (MARGINAL — gate condición 1)
  1. Source Serif 4         overlap 0.712
  2. Spectral               overlap 0.690   Δ 0.022  → EMPATE con el líder
  3. Frank Ruhl Libre       overlap 0.685   Δ 0.005  → EMPATE con el líder
  4. Crimson Pro            overlap 0.683   Δ 0.002  → EMPATE con el líder
  5. Libre Baskerville      overlap 0.674   Δ 0.009
  [control] Roboto         overlap 0.524
  [control] Montserrat     overlap 0.414
  [control] Oswald         overlap 0.391
  [control] Pacifico       overlap 0.386
```

**Condición 1 (separación medible):**
- Región "mente": sep = 0.270, banda **OK** (> 0.2). Cumple.
- Región "INTEGRATIVE PSYCHOLOGY": sep = 0.188, banda **MARGINAL** (0.1–0.2). No cumple stricto sensu — el cluster serif supera a los controles pero con margen insuficiente para el gate.

**Condición 2 (juicio visual de Samuel):** **PASA** (2026-06-05) — tiras en
`~/Desktop/fontid_gate_mente.png` y `~/Desktop/fontid_gate_integrative.png`.
Observación registrada en el juicio: los renders top-1 se ven más pesados que el
original (fino, alto contraste); el probing de pesos `wght` 300–700 (feature de
Fase A) es la causa probable del desempate pendiente — se espera que promueva a
Cormorant Garamond Light en "mente". **Veredicto: Fase A se planifica**, con el
probing de pesos como prioridad informada por esta evidencia.

**Observaciones:**
- Región 1 ("mente"): 5 glifos segmentados correctamente (sin puntos ni acentos — límite declarado del spike no aplica aquí). Empate real entre Libre Baskerville (0.747) y Cormorant Garamond (0.737), Δ = 0.010 < TIE_DELTA (0.030). Ambas son candidatas viables; el juicio visual de Samuel es el desempate correcto.
- Región 2 ("INTEGRATIVE PSYCHOLOGY"): 21 caracteres sin espacios → 21 glifos. La versalita espaciada genera un cluster muy plano: top-4 en empate (Δ acumulado = 0.029 entre posición 1 y 4). La separación MARGINAL es esperable: versalitas de caja alta tienen proporciones más genéricas entre familias serif, acercando el gap con sans como Roboto (0.524 vs lider 0.712 = gap 0.188). Ningún fallo de segmentación — los stems finos se binarizaron correctamente a esta resolución.
- Sin candidatas omitidas: los 24 TTFs del pool se descargaron y validaron sin errores de red.
- Tira visual "mente": crop 600×170 px | render Libre Baskerville 120pt escalado a 620×170 px.
- Tira visual "INTEGRATIVE PSYCHOLOGY": crop 960×100 px | render Source Serif 4 60pt escalado a 1054×100 px.

## Fase A — corrida de aceptación (2026-06-06)

```
Corpus: Google Fonts. Si la fuente original es comercial, esto es la
alternativa libre más cercana — no una identificación.

[REGIÓN 1] "mente" — type (score 0.947, baseline res=0.23px, var. altura=0.008, repetición usada)
  cluster: Serif — separación vs mejor de otra categoría: 0.176 (MARGINAL)
  1. Libre Baskerville        overlap 0.747 (wght 400)
  2. Noto Serif JP            overlap 0.733 (wght 500)   Δ 0.014  → EMPATE con el líder
  3. Lora                     overlap 0.663 (wght 400)   Δ 0.070
  4. Merriweather             overlap 0.659 (wght 600)   Δ 0.004
  5. PT Serif                 overlap 0.657 (wght 400)   Δ 0.002
  preview: C:\Users\simon\Desktop\logo_ale_fontid_r1.png

[REGIÓN 2] "INTEGRATIVE PSYCHOLOGY" — type (score 0.87, baseline res=0.4px, var. altura=0.028, repetición usada)
  cluster: Serif — separación vs mejor de otra categoría: 0.103 (MARGINAL)
  1. Lora                     overlap 0.726 (wght 600)
  2. PT Serif                 overlap 0.715 (wght 700)   Δ 0.011  → EMPATE con el líder
  3. Noto Serif               overlap 0.711 (wght 500)   Δ 0.004  → EMPATE con el líder
  4. Merriweather             overlap 0.709 (wght 600)   Δ 0.002  → EMPATE con el líder
  5. Libre Baskerville        overlap 0.706 (wght 700)   Δ 0.003  → EMPATE con el líder
  preview: C:\Users\simon\Desktop\logo_ale_fontid_r2.png

Aviso: zonas con texto caligráfico pueden no listarse arriba (el OCR no siempre emite región para handwriting). Usa --region/--text para forzarlas.
```

**Tiempos:** fría 42.8s / caliente 5.2s.

**OCR:** Detectó correctamente 2 regiones: "mente" y "INTEGRATIVE PSYCHOLOGY". La caligrafia "libre" no apareció como región separada — confirmado el límite declarado del spike (el OCR Windows no siempre emite región para handwriting). Ambas regiones tipográficas detectadas sin intervención manual.

**Pregunta 1 (pesos):** El probing de pesos NO cambió el líder de "mente": sigue siendo Libre Baskerville con overlap 0.747, pero ahora identificado como wght 400 (regular). Cormorant Garamond desapareció del top-5 — fue desplazado por Noto Serif JP (0.733, wght 500) y Lora (0.663, wght 400). Resultado comparado contra el spike:

| familia | spike (sin pesos) | aceptación (con pesos) | Δ |
|---|---|---|---|
| Libre Baskerville | 0.747 (implícito wght 400) | 0.747 (wght 400) | 0.000 |
| Cormorant Garamond | 0.737 (implícito wght 400) | **no aparece en top-5** | — |
| EB Garamond | 0.683 (implícito wght 400) | **no aparece en top-5** | — |
| Crimson Text | 0.668 | **no aparece en top-5** | — |
| Lora | 0.663 | 0.663 (wght 400) | 0.000 |

La hipótesis del gate (que el probing promovería Cormorant Garamond Light en "mente") **no se cumplió**. El pool del flujo automático es de 60 familias por popularidad GF vs. el SPIKE_POOL de 24 familias curadas — las garaldas (Cormorant Garamond, EB Garamond) pueden no haber entrado en el top-60 por popularidad o haber sido desplazadas por otros serifs más populares. El líder Libre Baskerville se mantiene estable en 0.747 con su peso regular.

Para Región 2, el líder cambió: Lora 0.726 wght 600 en vez de Source Serif 4 0.712 del spike. El probing de pesos sí impactó aquí — Lora a peso 600 supera a todos los candidatos del spike.

**Pregunta 2 (auto):** El flujo automático (OCR + classify_region) funcionó correctamente. Región 1 ("mente"): clasificada como `type` score 0.947 (alta confianza — baseline residual 0.23px muy bajo, altura casi uniforme, repetición de 'e' confirmada). Región 2 ("INTEGRATIVE PSYCHOLOGY"): clasificada como `type` score 0.87. La caligrafia de "libre" no fue detectada por OCR (comportamiento esperado y documentado).

**Previews:**
- `C:\Users\simon\Desktop\logo_ale_fontid_r1.png`
- `C:\Users\simon\Desktop\logo_ale_fontid_r2.png`

**Pendiente:** juicio de aceptación de Samuel.

### Corrida complementaria: `--category serif --pool 60` (2026-06-06)

El hallazgo de la corrida full-auto (el pool por popularidad general expulsa a las
garaldas) se confirmó y se resolvió con el pool por categoría:

```
[REGIÓN 1] "mente"
  1. Cormorant Garamond       overlap 0.753 (wght 500)   ← NUEVO LÍDER
  2. Libre Baskerville        overlap 0.747 (wght 400)   Δ 0.006  → EMPATE
  3-5. Noto Serif JP/KR/TC    overlap 0.733 (wght 500)   → EMPATE

[REGIÓN 2] "INTEGRATIVE PSYCHOLOGY"
  1. STIX Two Text            overlap 0.770 (wght 600)
  2. Crimson Pro              overlap 0.758 (wght 500)   → EMPATE
  3. Crimson Text             overlap 0.754 (wght 600)   → EMPATE
```

**La hipótesis del gate se confirma con el pool correcto:** el probing de pesos
promovió a Cormorant Garamond de 0.737 (wght 400, spike) a **0.753 (wght 500)**,
desplazando a Libre Baskerville del liderato. Visualmente (preview r1) Cormorant 500
es la más cercana al contraste fino del original.

**Hallazgo de producto:** el pool default por popularidad general (Serif+Sans+Display)
no contiene a las garaldas — para logos serif, `--category serif` es prácticamente
obligatorio. Candidato Fase A.x: elegir la categoría del pool automáticamente desde
las features del crop, o documentar `--category` como flag recomendado.

## Recomposición híbrida manual — prototipo de Fase B (2026-06-07)

Samuel pidió que el fullres fuera "perfecto". El fullres a resolución nativa (838 KB)
es fiel en la caligrafía pero conserva el límite estructural: serifas empastadas en
"mente" y trazos temblorosos en "INTEGRATIVE PSYCHOLOGY". Se ejecutó a mano lo que
Fase B propone automatizar:

1. **Boxes:** `detect_regions` (OCR) + `segment_glyphs_with_boxes` sobre el original →
   bboxes absolutos de las 2 regiones y de los 26 glifos (5 + 21).
2. **Caligrafía:** regiones de texto enmascaradas en blanco (pad 6px) y re-vectorizado
   contour winner B a resolución nativa → 5 contornos (libre+swash, punto de la i, 3 pájaros).
3. **Tipografía desde TTF:** fontTools `SVGPathPen` + `BoundsPen`. "mente" con
   Cormorant Garamond 500, "INTEGRATIVE PSYCHOLOGY" con STIX Two Text 600 (los líderes
   de la corrida `--category serif`). **Colocación glifo a glifo**: escala COMÚN por
   región (mediana de altura original/altura font-units — misma filosofía que la métrica
   de matching), centro-x y fondo del bbox alineados al glifo original. El letterspacing
   del logo sale gratis de las posiciones originales.
4. **Verificación cuantitativa:** re-segmentando el render — ratio de altura mediana
   1.000, delta centro-x 0.0px, delta baseline 0.0px en las dos regiones. XOR binario
   global con tolerancia 2px: **1 píxel en disputa, 0 clusters ≥30px** (nada recortado
   por la máscara, nada sobrante).

**Resultado:** `C:\Users\simon\Desktop\Ale\logo_ale_perfecto.svg` — 237 KB (vs 838 KB),
serifas nítidas con contraste de trazo real, caligrafía intacta.
Preview: `C:\Users\simon\Desktop\Ale\logo_ale_perfecto_preview.png`.

### Ronda 2 de suavizado (feedback de Samuel: "le falta un poquito")

Barrido sobre la caligrafía solamente (el texto TTF ya es curva perfecta):
RDP 0.8/1.2, chaikin 3, blur 5 — y dos variantes con **filtro gaussiano
circular sobre los puntos del contorno ANTES del RDP** (σ=2 y σ=3), que mata
el ruido de píxel sin deformar la forma (técnica nueva, no está en
`vectorize.py` — candidata Fase 1.x como flag `--contour-sigma`).

| variante | XOR vs orig (px) | seg. C | tamaño grupo |
|---|---|---|---|
| actual (winner B nativo) | 3 939 | 5 124 | 223 KB |
| rdp 0.8 | 4 216 | 1 700 | 74 KB |
| rdp 1.2 | 4 523 | 1 252 | 54 KB |
| **filtro σ=2 + rdp 0.8** | **4 820** | **1 504** | **65 KB** |
| filtro σ=3 + rdp 0.8 | 5 109 | 1 484 | 65 KB |

Juicio visual a 4× (diagonal larga, pájaro chico, lazo del 'e'): **σ=2 gana** —
bordes calmados sin perder el pico del pájaro ni los cruces finos; σ=3 ya
ablanda las uniones. La pérdida de fidelidad XOR (+22% sobre 3 939) es toda
de borde sub-píxel, sin clusters.

**Entregable final: 81 KB.** Re-verificado: ratio altura 1.000, deltas 0.0px,
XOR global con tolerancia 2px = 1 píxel, 0 clusters.
Script: `scripts/scratch_smooth_v2.py` (el barrido: `scripts/scratch_smooth_sweep.py`).

### Ronda 3: bake-off de la 'e' (feedback de Samuel: "muy barrigonas")

Samuel detectó que las 'e' de Cormorant Garamond no calzan: el ojo es más
grande y el lomo derecho más redondo que el original. Bake-off de 38 familias
serif cacheadas (todos los pesos), palabra colocada glifo a glifo en posición
final, IoU exacto por glifo (`scripts/scratch_e_bakeoff.py`):

| familia/peso | e-IoU | word-IoU |
|---|---|---|
| Cormorant Garamond 400 | 0.789 | 0.701 |
| Cormorant Garamond 500 (anterior) | 0.780 | 0.721 |
| **Nanum Myeongjo 400** | 0.763 | 0.705 |
| Libre Baskerville 400 | 0.737 | **0.800** |

**Hallazgo para Fase B:** el IoU crudo NO captura la queja perceptual — CG
seguía ganando en métrica mientras Samuel veía la barriga. El overlay por
glifo (verde=original, magenta=candidata) sí la expone: ojo de CG demasiado
grande; Nanum Myeongjo calza crossbar y ojo exactos. La métrica ordena el
cluster; el desempate fino es visual — confirmación N=2 del principio del spec.

Opciones presentadas en contexto real (A: CG500, B: Nanum Myeongjo 400,
C: Libre Baskerville 400, D: franken CG+e de NM). **Samuel eligió B.**
`scripts/scratch_rebuild_text.py` regeneró el grupo de texto: mente →
Nanum Myeongjo 400, INTEGRATIVE PSYCHOLOGY → STIX Two Text 600 (sin cambio).

Re-verificado: ratio 1.000, deltas 0.0px; XOR global = 1 cluster de 76px
(astilla de 2px en el stem de la 'm': la 'm' de NM es ~2px más angosta —
invisible). **Entregable final: 79 KB.**

**Evidencia para Fase B:** las tres condiciones del spec se tocaron aquí en versión
manual — la recomposición glifo-a-glifo con escala común + alineación bbox da registro
exacto sin ajuste fino iterativo. El paso que Fase B tendría que automatizar y que aquí
fue juicio humano: elegir QUÉ regiones recomponer y con qué familia/peso (aquí: los
líderes de la corrida de aceptación, elegidos visualmente por Samuel/preview).
Scripts del prototipo: `docs/calibration/scripts/` (paths de usuario hardcodeados —
son evidencia de calibración, no producto).

## Fase B v0.1 — corrida de aceptación (2026-06-07)

El producto (`recompose.py`, replay puro) contra el prototipo manual, spec §9.1:

```
python recompose.py logo_ale.jpeg -o logo_ale_v01.svg
  --font "mente=Nanum Myeongjo:400"
  --font "INTEGRATIVE PSYCHOLOGY=STIX Two Text:600"
  --contour-sigma 2 --category serif
```

**Costura reportada:** "mente" → recompone (type 0.95); "INTEGRATIVE PSYCHOLOGY" →
recompone (type 0.87); "libre" ausente del OCR (límite documentado). 5 contornos de
caligrafía + 26 glifos. Preview y comandos de corrección emitidos (las alternativas
del ranking serif real por región: Cormorant Garamond 500, Libre Baskerville 400, …).

**XOR producto-vs-prototipo** (render contra render, tolerancia 2px):
**0 clusters ≥30px, 0 píxeles en disputa.** El criterio era "cero clusters";
el resultado fue indistinguibilidad total — la astilla de la 'm' se canceló
como el spec predijo (mismas fuentes, mismo sigma).

**Registro por glifo contra el original:** mediana ratio de altura 1.000,
Δcentro-x +0.0px, Δbaseline +0.0px en ambas regiones — idéntico al prototipo.

**Nota honesta del spec §9:** esto valida costura, compositor y contrato (el
reproductor de decisiones humanas reproduce). La validación del *juicio*
(sesión/chooser) es la aceptación de B.2, con su propia evidencia.

Pendiente: juicio de aceptación de Samuel sobre la corrida.
