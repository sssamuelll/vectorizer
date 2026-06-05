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
