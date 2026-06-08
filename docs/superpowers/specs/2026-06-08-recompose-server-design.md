# Spec B1 — server FastAPI (diseño)

**Fecha:** 2026-06-08
**Estado:** spec hijo de `2026-06-08-recompose-backend-design.md` (padre B, §3 diseño B1 diferido).
Segundo y último entregable del backend. **Vetado por la junta de 6 sillas** sobre el draft de B
(no requiere junta propia; el spec-review + reviews por tarea cubren la calidad).
**Depende de:** Spec A (PR #3) + Spec B0 (PR #4) MERGEADOS — `resolve_choices`/`ChoiceResolution`,
`compose_hybrid_svg`/`ComposeResult`, `load_image_bgr_from_bytes` ya en main.
**Aceptación dura:** `/compose` por `TestClient` sobre los bytes del logo de Ale → SVG
**byte-idéntico (SHA256)** a `logo_ale_v01.svg`.

---

## 0. Decisiones (brainstorming + junta)

- **Sin token** (loopback + uuid; Vex cortó `/api/image`).
- **Escotilla "otra familia" diferida** — 2 endpoints.
- **`/analyze` devuelve familias candidatas, NO glifos** (el overlay lo define C).
- **v1 endurecimiento mínimo:** SIN lock OCR (Halberg midió que winocr no racea aquí) y SIN timeout
  explícito de request (los timeouts de urllib ya acotan `/analyze`). Ambos → B1.x si una corrida
  real duele.

## 1. Módulos

```
server/
├── __init__.py
├── __main__.py   `python -m server` → uvicorn.run("server.app:app", host="127.0.0.1", port=8000)
├── app.py        FastAPI: lifespan, los 2 endpoints, CORS, el store inline (dict + lock)
└── models.py     DTOs Pydantic del wire, construidos desde las dataclasses + test de isomorfismo
```
Importa del core (sin duplicar): `fontid.{analyze_regions, RegionAnalysis, RankEntry,
count_effective_colors, CACHE_DIR_DEFAULT}`, `recompose_core.{seam_decision, resolve_choices,
compose_hybrid_svg, FontKeyError}`, `vectorize.load_image_bgr_from_bytes`. **Endpoints `def`
(sync)** — FastAPI los corre en el threadpool de anyio (verificado por Halberg: sin conflicto de
event loop con el `asyncio.run` interno de winocr).

## 2. El store (inline en `app.py`)

```python
@dataclass
class Session:
    raster: "np.ndarray"   # BGR decodificado del upload
    regions: list          # [RegionAnalysis]
    width: int
    height: int

_SESSIONS: dict[str, Session] = {}
_LOCK = threading.Lock()

def _put(sess) -> str:                 # imageId = uuid4().hex (no singleton, no adivinable)
    sid = uuid.uuid4().hex
    with _LOCK: _SESSIONS[sid] = sess
    return sid

def _get(sid):                         # None si no existe / expiró (reinicio)
    with _LOCK: return _SESSIONS.get(sid)
```
**Sin TTL/GC en v1** (los índices son imageId-scoped; un `imageId` que no existe → 404; el frontend
re-sube, decisión documentada de C de no re-aplicar índices viejos a un imageId nuevo). El `lifespan`
hace `_SESSIONS.clear()` en shutdown — el raster (material de cliente) no persiste un reinicio.

## 3. `POST /api/analyze` (multipart `file`)

1. `data = await file.read()` → `load_image_bgr_from_bytes(data)`. `None` (vacío/ilegible) → **415**.
2. `count_effective_colors(raster)` → `colorWarning` (string si supera el umbral, `null` si no).
3. `regions = analyze_regions(raster)`.
4. Por región, **deriva** la vista (no es estado nuevo — se lee de `seam_decision` + `ranking`):

```python
def _decision(r):
    d = seam_decision(r, has_font=False)
    if not d.recompose:
        kind = "vectorized" if r.classification != "type" else "no_font"
        return kind, None, None, d.reason
    empate = len(r.ranking) > 1 and r.ranking[1].tie
    if empate:
        band = ([r.ranking[0]] + [e for e in r.ranking[1:] if e.tie])[:4]
        return "tie", band, None, None
    return "leader", None, r.ranking[0], None
```
5. `imageId = _put(Session(raster, regions, w, h))`.
6. Devuelve `AnalyzeResponse`:
```jsonc
{ "imageId":"...", "width":W, "height":H, "colorWarning":null,
  "regions":[{ "index":0, "bbox":[x0,y0,x1,y1], "text":"mente",
    "classification":"type", "classScore":0.9, "decision":"tie",
    "candidates":[{"family":"Nanum Myeongjo","wght":400,"score":0.78,"tie":true}],
    "chosen":null, "reason":null }] }
```
`decision:"leader"` → `chosen:{family,wght}`. `vectorized`/`no_font` → `reason`. **Candidatas sin glifos.**

## 4. `POST /api/compose` (json)

`{ "imageId":"...", "choices":{"0":{"family":"Nanum Myeongjo","wght":400}}, "contourSigma":2.0 }`.
**Dueño de la política = el `resolve_choices` compartido de B0** (mismo que `main()`):
1. `sess = _get(imageId)`; `None` → **404**.
2. `explicit = {int(k): (v.family, v.wght) for k,v in choices.items()}`; clave no-índice o fuera de
   `range(len(sess.regions))` → **400**.
3. `resolved = resolve_choices(sess.regions, explicit)`.
4. `if not resolved.recomp_idx:` → **422** ("nada que recomponer") — **antes** del check de pendientes
   (orden de `main()`).
5. `if resolved.pendientes:` → **400** con `{pendientes:[{index, text}]}`.
6. `try: res = compose_hybrid_svg(sess.raster, sess.regions, resolved.effective,
   resolved.recomp_idx, contourSigma, CACHE_DIR_DEFAULT)` ; `FontKeyError` → **422** con el detalle.
7. Devuelve `{ "svg": res.svg_text, "provenance": res.provenance,
   "ignoradas":[{index, text}] }` — `ignoradas` (choices sobre región no-recompuesta) espeja el
   `[WARN]` del CLI: nunca se traga en silencio.

## 5. El contrato — DTOs derivados + isomorfismo (Richter/Vex)

`models.py` define los DTOs Pydantic del wire (`RankEntryDTO`, `RegionDTO`, `AnalyzeResponse`,
`ComposeRequest`, `ComposeResponse`, `ErrorResponse`) **construidos desde las dataclasses** con un
mapeo explícito (p.ej. `RegionDTO.from_region(r, decision_view)`). `bbox` se tipa
`tuple[int,int,int,int]` (aridad fija) y `glyph_boxes` (interno, NO va al wire de candidatas) como
`list[tuple[int,int,int,int]]`.

**Test de isomorfismo** (la garantía real, no censo de nombres): asierta que **cada campo** de
`RegionAnalysis` y `RankEntry` está o **mapeado** a su DTO o en una lista de **excluidos-con-razón**
(p.ej. `glyph_boxes` excluido del wire: "interno, el server compone server-side"). Si la dataclass
gana un campo no listado, el test falla hasta que alguien decida si el wire lo lleva. Eso cierra el
salto dataclass→DTO con preservación de forma.

## 6. Errores (forma Pydantic en el OpenAPI)

| caso | HTTP | cuerpo |
|---|---|---|
| `imageId` inexistente/expirado | 404 | `{error:"imageId desconocido"}` |
| empate sin elección | 400 | `{error, pendientes:[{index,text}]}` |
| clave de `choices` inválida/fuera de rango | 400 | `{error, detail}` |
| `FontKeyError` (familia/peso/glifo/TTF) | 422 | `{error, detail}` |
| nada que recomponer (`recomp_idx` vacío) | 422 | `{error:"nada que recomponer"}` |
| upload vacío/ilegible | 415 | `{error, detail}` |

**413 fuera de v1** (single-user loopback — mismo argumento que el no-token).

## 7. Testing y aceptación

- **Aceptación dura:** `TestClient`: POST los **bytes** de `logo_ale.jpeg` a `/api/analyze` → leer
  `regions`, resolver índices por texto (`mente`, `INTEGRATIVE PSYCHOLOGY`) → POST `/api/compose`
  con `{idx_mente:{Nanum Myeongjo,400}, idx_integr:{STIX Two Text,600}}`, `contourSigma:2` → el `svg`
  devuelto es **byte-idéntico** a `logo_ale_v01.svg`. (Requiere las fuentes cacheadas — ya lo están.)
- Tests de error: 404 (imageId basura), 400 (región empate sin choice), 422 (familia inexistente →
  FontKeyError; y `recomp_idx` vacío), 415 (upload de bytes basura).
- Test de la derivación `_decision` con fixtures sintéticos (tie/leader/no_font/vectorized).
- Test de isomorfismo dataclass↔DTO. Test del store (put/get; un `imageId` desconocido → None;
  shutdown limpia `_SESSIONS`).
- Los **112 tests existentes siguen verdes** (B1 añade superficie; no toca core/CLI).
- Deps nuevas: `fastapi`, `uvicorn[standard]`, `python-multipart`, `httpx` (TestClient).

## 8. No-goals de B1 (v1)

Sin token · sin `/api/image`/`/api/families`/render de candidata arbitraria · sin glifos en
`/analyze` · sin TTL/GC del store · sin lock OCR ni timeout explícito de request (B1.x) · sin
static-serving del frontend ni CORS de producción (C) · sin 413/límite de tamaño · sin persistencia.

## 9. Riesgos

| riesgo | disposición |
|---|---|
| el web path no da byte-idéntico al CLI | aceptación por TestClient (§7) es el gate; el decode compartido (B0) + `resolve_choices` compartido (B0) lo garantizan por construcción |
| `/analyze` lento/colgado con red caída | acotado por los timeouts de urllib (20-30s/familia); timeout explícito diferido a B1.x |
| store sin TTL crece en una corrida larga | single-user; shutdown limpia; TTL diferido a B1.x |
| primer server/deps en CI | aislado a `server/`; los 112 tests del core/CLI no dependen de fastapi |
| índice colgante tras re-subida (Voronov B-II) | índices imageId-scoped; cross-imageId es contrato de C (no re-aplicar índices viejos) |
```
