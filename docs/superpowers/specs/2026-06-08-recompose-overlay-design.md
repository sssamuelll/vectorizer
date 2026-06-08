# Spec C0 — `POST /api/overlay` (geometría del overlay fiel)

Fecha: 2026-06-08
Arco: recompose como app web (A → B → **C**). C se parte en **C0 (este spec, backend)** + C1 (frontend).
Depende de: Spec A (`region_glyph_paths`, `resolve_ttf`, `compose_hybrid_svg` en `recompose_core`), Spec B1 (`server/{app,models}.py`, el store, el envelope de error).

## 1. Por qué existe

El frontend (C1) pinta la candidata en **magenta a tamaño completo sobre el original** — la superficie de juicio. Para que el juicio valga, el overlay tiene que ser **fiel**: la geometría que el ojo mira tiene que ser la misma que `/compose` va a producir si eliges esa candidata. Si difieren, el ojo juzga A y descarga B.

El prototipo de diseño simula el overlay con texto CSS (un `<span>` en la fuente). Eso no posiciona los glifos en los `glyph_boxes` originales y no coincide con `compose`. La geometría fiel sale de un solo sitio: el mismo `region_glyph_paths` que `compose_hybrid_svg` usa. C0 expone esa geometría por un endpoint para que el front no la re-derive en TS.

Decisión tomada en brainstorming: **el backend dibuja los glifos** (no el front desde la fuente con opentype.js). Y **`/analyze` no se toca** — precomputar las ≤4 candidatas ahí lo volvería lento (bajaría TTFs que el usuario quizá nunca previsualiza). El overlay es **lazy**: el front lo pide al pasar el cursor / teclear, y prefetchea la región activa (eso es trabajo de C1).

## 2. El contrato

### Request

```
POST /api/overlay
{ "imageId": "<hex>", "regionIndex": 0, "family": "STIX Two Text", "wght": 600 }
```

`extra=forbid`. `family`/`wght` pueden ser cualquiera (la escotilla "otra familia" elige fuera del menú; el backend resuelve o devuelve 422, igual que `/compose`). La política de qué se muestra es del front; el backend computa el hecho.

### Response (200)

```json
{ "glyphs": [ { "d": "M…Z", "transform": "matrix(…)" }, … ] }
```

Los `d`/`transform` están en **coordenadas de imagen completa** (las mismas que el `<g class="type">` del compose; el `transform` coloca cada glifo en su `glyph_box`). El front envuelve los paths en un `<svg viewBox="0 0 W H">` sobre el raster (W×H que ya tiene de `/analyze`), con `fill` magenta. El color **no viaja**: la geometría es lo único que el juicio necesita; el magenta lo pone el front (regla 5 del diseño: magenta exclusivo de la capa candidata).

### Errores (envelope `{ "detail": { "error": … } }`, idéntico a B1)

| HTTP | Cuándo |
|---|---|
| 404 | `imageId` desconocido (expiró / reinicio del server) |
| 400 | `regionIndex` fuera de rango, o región sin texto tipográfico (vectorized / sin `glyph_boxes` / la costura no garantiza `len(chars)==len(boxes)`) |
| 422 | `FontKeyError`: peso/familia no resoluble, sin cmap, sin glifo para un char (la misma falla que `/compose` ante una fuente mala) |
| 422 (Pydantic) | body inválido (`extra=forbid`, tipos) — comportamiento estándar de FastAPI |

## 3. El cambio de core: un solo dueño de la geometría por región

`compose_hybrid_svg` resuelve la geometría de cada región inline (recompose_core.py:260-267). Se extrae esa unidad a una función de core que **compose y overlay comparten**, para que el overlay no duplique la política de "quita espacios" ni la resolución de TTF:

```python
def region_overlay_paths(region, family, wght, cache_dir):
    """[(d, transform)] de UNA región con una candidata, en coords de imagen
    completa. La unidad por región que compose_hybrid_svg usa, extraída para que
    el overlay del backend (C0) la reuse: el ojo juzga exactamente lo que
    /compose va a producir. Devuelve (pairs, ttf_path) — compose necesita el
    ttf_path para el sha de procedencia. FontKeyError si la fuente falla."""
    ttf = resolve_ttf(family, wght, cache_dir)
    chars = [c for c in region.text if not c.isspace()]
    return region_glyph_paths(ttf, chars, region.glyph_boxes, family), ttf
```

`compose_hybrid_svg` pasa a llamarla en su loop:

```python
for i in recomp_idx:
    r = regions[i]
    family, wght = choices[i]
    pairs, ttf = region_overlay_paths(r, family, wght, cache_dir)
    sha = hashlib.sha256(ttf.read_bytes()).hexdigest()[:16]
    provenance.append(f"{family}:{wght} sha256:{sha}")
    glyph_pairs.extend(pairs)
    mask_boxes.append(r.bbox)
```

Es un refactor puro: el test byte-idéntico de compose (sobre el logo de Ale) sigue cubriéndolo. La alternativa — duplicar las 3 líneas en el endpoint — se rechaza: `chars = [c for c in r.text if not c.isspace()]` es política, y duplicada deriva.

## 4. El endpoint

`server/app.py` agrega:

```python
@app.post("/api/overlay", response_model=models.OverlayResponse)
def overlay(req: models.OverlayRequest):
    sess = _get(req.imageId)
    if sess is None:
        raise HTTPException(404, detail={"error": "imageId desconocido"})
    if not (0 <= req.regionIndex < len(sess.regions)):
        raise HTTPException(400, detail={"error": f"regionIndex fuera de rango: {req.regionIndex}"})
    r = sess.regions[req.regionIndex]
    if r.classification != "type" or not r.glyph_boxes \
            or len([c for c in r.text if not c.isspace()]) != len(r.glyph_boxes):
        raise HTTPException(400, detail={"error": "región sin texto tipográfico"})
    try:
        pairs, _ = region_overlay_paths(r, req.family, req.wght, CACHE_DIR_DEFAULT)
    except FontKeyError as e:
        raise HTTPException(422, detail={"error": str(e)})
    return models.OverlayResponse(
        glyphs=[models.GlyphPath(d=d, transform=tr) for d, tr in pairs])
```

El endpoint es **sync** (corre en el threadpool de anyio, como `/analyze` y `/compose`). Reusa `CACHE_DIR_DEFAULT` (la misma caché de fuentes que compose; el TTF de la candidata se baja una vez y queda cacheado para el compose final). No escribe en el store.

La validación del char-count (`len(chars)==len(glyph_boxes)`) replica la precondición que `region_glyph_paths` asume ("la costura ya lo garantizó"). Para una región `type` válida siempre se cumple; el guard convierte un caso imposible en 400 honesto en vez de 500.

## 5. DTOs (`server/models.py`)

```python
class OverlayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    imageId: str
    regionIndex: int
    family: str
    wght: int

class GlyphPath(BaseModel):
    d: str
    transform: str

class OverlayResponse(BaseModel):
    glyphs: list[GlyphPath]
```

El test de isomorfismo existente vigila las DTOs derivadas de dataclasses; `GlyphPath` es nuevo y plano (no deriva de ninguna dataclass), así que no entra al censo de isomorfismo — pero su contenido se prueba por la aceptación fiel (§6).

## 6. Aceptación

**Dura (fidelidad — la razón de existir).** Sobre el logo de Ale (`load_image_bgr` → `analyze_regions`), por cada región en empate y por **cada candidata de su banda**: los `glyphs` de `/api/overlay` (vía TestClient) son **idénticos** (par `d`+`transform` por glifo, en orden) a los paths del `<g class="type">` que `compose_hybrid_svg` produce al componer **esa sola región** con esa candidata (`choices={i:(family,wght)}`, `recomp_idx=[i]`). Eso prueba: lo que el ojo juzga == lo que se descarga.

**Errores.**
- 404: `imageId` inventado.
- 400: `regionIndex` negativo y `>= len(regions)`; región `vectorized` (sin texto tipográfico).
- 422: familia inexistente en GF; peso no disponible para una familia real.
- 422 Pydantic: body con campo extra / tipo inválido.

**No-regresión.** La suite de B1 (134 tests) sigue verde; el byte-idéntico de compose sobre el logo de Ale sigue verde tras el refactor de `region_overlay_paths`.

## 7. Fuera de alcance (C0)

- `/analyze` no cambia (sigue devolviendo familias, sin glifos).
- Sin precompute, sin caché de overlay en el server, sin TTL. El prefetch y la caché por `(regionIndex, family, wght)` son del front (C1).
- El color (magenta) no viaja. Una región por llamada.
- El frontend entero (portar el prototipo, cablear, estados) es C1, su propio spec.

## 8. Notas de implementación

- Stack: el server ya existe (B1). C0 añade una función a `recompose_core.py`, un endpoint a `server/app.py`, tres DTOs a `server/models.py`, y tests a `tests/test_server.py` (+ los del core si aplica al refactor).
- Proceso: subagent-driven (implementer + spec review + quality review por tarea). **Git safety:** los subagentes comparten el working tree — prohibido `git checkout/switch/reset/stash` en cualquier prompt de subagente.
- El refactor de `compose_hybrid_svg` se hace y se verifica con el byte-idéntico ANTES de añadir el endpoint, para aislar la causa si algo se mueve.
