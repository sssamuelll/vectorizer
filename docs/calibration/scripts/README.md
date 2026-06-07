# Scripts del prototipo de recomposición híbrida (2026-06-07)

Evidencia de calibración, no producto: paths de usuario hardcodeados y imports
relativos a la raíz del repo (correr con `python docs/calibration/scripts/<x>.py`
DESDE la raíz, con `fontid.py`/`vectorize.py` importables).

Orden del flujo:

1. `scratch_boxes.py` — OCR + glyph boxes absolutos → `_boxes.json`
2. `scratch_perfect.py` — máscara + caligrafía nativa + tipografía TTF → SVG híbrido
3. `scratch_check.py` — render + zooms comparativos
4. `scratch_measure.py` — verificación cuantitativa (escala/centro/baseline)
5. `scratch_diff.py` — XOR binario global (trazos perdidos/sobrantes)
6. `scratch_final.py` — preview final lado a lado

(`scratch_render.py` / `scratch_crops.py`: diagnóstico inicial del fullres.)

Contexto y resultados: `../2026-06-05-logo-libre-mente.md`, sección
"Recomposición híbrida manual — prototipo de Fase B".
