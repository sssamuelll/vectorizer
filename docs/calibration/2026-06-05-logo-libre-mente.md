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

## Implicaciones acumuladas para Fase 2

- El router debe tolerar 3-5 colores efectivos en imágenes que son conceptualmente
  bicolores (JPEG sucio) antes de declarar `graphic`.
- El caso "logo de tinta única" refuerza que el paso de grosor-de-trazo (o un sustituto)
  importa: este logo tiene trazos finos caligráficos → handwriting fue lo correcto, pero
  un logo monocolor de bloques gruesos seguiría necesitando `graphic`.
