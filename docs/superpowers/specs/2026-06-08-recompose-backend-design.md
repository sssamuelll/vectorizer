# Spec B — backend FastAPI (diseño v2, post-junta) — PADRE B0/B1

**Fecha:** 2026-06-08 (DRAFT mañana; v2 misma tarde, tras junta de 6 sillas)
**Estado:** v2 — **descompuesto en B0 (core hardening) → B1 (server)** por veredicto convergente
de Richter/Stride/Voronov, aceptado por Samuel. Este documento es el **padre de B**: decisiones,
síntesis de la junta, reparto, y el diseño diferido de B1.
**Specs hijos:** `2026-06-08-recompose-core-hardening-design.md` (B0, implementable ya). B1 (server)
se especifica cuando B0 esté mergeado.
**Padre del arco:** `2026-06-07-recompose-web-app-design.md` (maestro v2, A→B→C).
**Depende de:** Spec A MERGEADO (PR #3). **Junta:** Halberg, Serrano, Voronov, Richter, Stride, Vex.

---

## 0. Decisiones (brainstorming + junta)

1. **Sin token en B** (Vex cortó `/api/image`; loopback + uuid).
2. **Escotilla "otra familia" diferida** — B = `/analyze` + `/compose`.
3. **B descompuesto en B0 → B1** (post-junta). B0 = los cambios de core/lib que el server
   necesita y que tienen aceptación CLI-byte-idéntica; B1 = el server. Dos merges, riesgos separados.
4. **`/analyze` devuelve familias candidatas, NO glifos pre-renderizados** (post-junta). El overlay
   de glifos lo define C cuando exista y pueda validar el formato visualmente.

## 1. Síntesis de la junta — convergencias y disposición

Ordenadas por nº de sillas (la convergencia es la señal).

**① La política está duplicada — la máquina de estados nunca se extrajo. 4 sillas (Voronov, Serrano,
Vex, Richter). BLOCKER → B0.** Spec A extrajo los *verbos* pero dejó la *gramática* (`empate>líder>
error`) inline en `main()` (`recompose.py:205-241`; predicado de empate `ranking[1].tie` en :229).
El §5 del draft la re-transcribía → dos dueños divergibles, y la byte-identidad no lo detecta (el
logo de Ale no ejerce el caso divergente). Serrano probó además que el draft **invertía el orden de
`has_font`** vs `main()`. **Disposición:** extraer `resolve_choices(regions, choices) → ChoiceResolution`
a `recompose_core` (B0), que `main()` Y `/compose` importen. Un dueño real.

**② El índice es identidad inestable. 2 sillas (Voronov B-II, Serrano). Disposición de diseño (B1+C).**
El `imageId` mata la colisión de raster, pero la clave `"0"` indexa `regions[0]` server-side; si
expira y el frontend re-sube, el OCR re-segmenta → índices colgantes → compose contra la región
equivocada. **Disposición:** índices son **imageId-scoped** (estables dentro de un `/analyze`); **B1
difiere TTL/GC** (sin expiración en v1, solo shutdown-cleanup) → el `imageId` vive lo que dure el ojo
(la tarea es ilimitada); el dangling cross-imageId es **contrato documentado para C** (no re-aplicar
índices viejos a un `imageId` nuevo).

**③ La invariante hash-raster apuntaba al oráculo equivocado. 3 sillas (Halberg medido, Serrano,
Richter). BLOCKER → B0 (decode compartido).** `load_image_bgr` (vectorize.py:33-52) usa
`cv2.imread(IMREAD_UNCHANGED)` + composición alpha/16bit/gris — NO `imread` crudo. El test del draft
comparaba contra `imread` default. **Refinamiento medido (2026-06-08, en esta máquina):**
`imread(UNCHANGED)` e `imdecode(UNCHANGED)` **ignoran ambos el EXIF** y dan array idéntico (solo
`imread` default aplica EXIF). → **Disposición:** extraer el post-decode de `load_image_bgr` a una
función compartida y decodificar bytes vía `imdecode(UNCHANGED)` + misma post-proc (B0). **NO se
necesita restringir a PNG**: medido byte-idéntico para el logo de Ale (JPEG) Y para JPEG con EXIF.
El único supuesto: el upload lleva los **bytes originales del archivo** (no un canvas re-encodeado) — eso es de C.

**④ B es dos entregas. 2 sillas (Richter, Stride). → B0/B1.** El fix `.tmp` tiene aceptación propia
(corrupción de caché, sin server), dependencia propia (ya vivo en `main`), blast radius propio
(`fontid`). Halberg corrigió: el sitio primario es **`:371`** (camino de `/analyze`), no `:253`;
`:288` es global (metadata). Son **tres** arreglos con perfiles distintos.

**⑤ `/analyze` hacía demasiado. 4 sillas (Stride, Vex, Richter, Voronov). → diferido.** Precomputar
glifos `{d,transform}` mete render en `/analyze`, sobre el camino con red, congela el contrato del
overlay antes de C, y nadie garantiza que coincidan con los de `/compose` (Voronov: el ojo juzga A,
descarga B). **Disposición:** `/analyze` devuelve `candidates:[{family,wght,score,tie}]` (lo que
`analyze_regions` ya da). Overlay de glifos → C/B1.x.

**Micro absorbido:** `cache_dir=CACHE_DIR_DEFAULT` explícito a `compose_hybrid_svg` · el test de
isomorfismo es censo de nombres, no preservación de valor (Richter) → DTOs **derivados** de las
dataclasses (Vex), no redeclarados → el isomorfismo se vuelve estructural · `store` inline en `app.py`
(no módulo) · `decision` **derivado** de `(seam_decision, ranking)`, no enum-máquina · 413 fuera
(single-user loopback, mismo argumento que el no-token), 415 dentro · `/compose` espeja el `[WARN]`
de `main()` para choices sobre región no-recompuesta · lock OCR quirúrgico en `fontid.py:827` con
comentario honesto, o diferido (Halberg lo midió inerte).

## 2. El reparto B0 → B1

| | qué | aceptación | ship |
|---|---|---|---|
| **B0** | core hardening (3 cambios, CLI-byte-idéntico): `.tmp` en 3 sitios (fontid); extraer `resolve_choices` a `recompose_core`; decode-desde-bytes compartido en `vectorize` | el CLI sigue dando 0px + test de concurrencia de caché | primero |
| **B1** | server FastAPI: `/analyze` + `/compose`, store inline (mapa+shutdown), aceptación byte-idéntica por `TestClient` | `/compose` por TestClient == `logo_ale_v01.svg` | tras B0 |

B0 mergeable solo (CLI verde, sin server). B1 lo asume. Detalle de B0 en su spec hijo.

## 3. B1 — diseño diferido (la junta ya lo pagó)

Para que B1 no re-pague:
- **Endpoints:** `POST /api/analyze` (multipart → decode-compartido → invariante hash-raster anclada a
  `load_image_bgr` → `analyze_regions` → por región `decision` derivado + `candidates:[{family,wght,
  score,tie}]` SIN glifos → guarda `(raster, regions, w, h)` bajo `uuid4`). `POST /api/compose`
  (`{imageId, choices, contourSigma}` → `resolve_choices` (el MISMO del core) → `compose_hybrid_svg(...,
  cache_dir=CACHE_DIR_DEFAULT)` → `{svg, provenance}`).
- **Estado:** store inline = `dict[str, SessionEntry]` + lock (cubre get/set/iteración/shutdown) +
  shutdown-cleanup. **Sin TTL/GC en v1** (difiere ②). Mapa uuid (mata Voronov B3 del raster).
- **Política:** `/compose` usa `resolve_choices`; `pendientes` → 400; `ignoradas` (choices sobre región
  no-recompuesta) → lista informativa en la respuesta (espeja el `[WARN]`). Orden de guards:
  `recomp_idx` vacío → 422 ANTES del check de pendientes (espeja `main():210`).
- **Errores (OpenAPI):** 404 (imageId), 400 (empate sin elección), 422 (`FontKeyError` / nada que
  recomponer), 415 (`imdecode` None). 413 diferido.
- **Contrato:** DTOs Pydantic **derivados** de `RegionAnalysis`/`RankEntry` (no redeclarados); el
  isomorfismo es estructural. `bbox` tupla de aridad fija, `glyph_boxes` = `list[tuple[...]]`.
- **Concurrencia:** lock OCR quirúrgico en `fontid.py:827` (prudencia, Halberg lo midió no-racea), o
  diferido. Sin pool anidado nuevo (el `ThreadPoolExecutor(8)` de `prepare_pool_weights` ya existe).
  Timeout de request (§5④ del maestro) — definir en B1.
- **Deps:** `fastapi`, `uvicorn[standard]`, `python-multipart`, `httpx`.
- **Diferido a B1.x:** glifos en `/analyze`, TTL/GC, 413, `colorWarning` como gate (es display de C),
  timeout fino.

## 4. No-goals de B (todas las fases)

Sin frontend/static-serving (C) · sin `/api/image`, `/api/families`, `/render-candidate` · sin token
· sin persistencia/DB · sin paridad de píxel cross-rasterizador (el ojo re-juzga en C) · sin
multi-imagen con UI.

## 5. Riesgos vivos

| riesgo | disposición |
|---|---|
| política duplicada (espejo de main) | `resolve_choices` al core (B0) — un dueño |
| índice colgante tras re-análisis | índices imageId-scoped + sin TTL v1; cross-imageId es contrato de C |
| raster post-multipart ≠ disco | decode compartido anclado a `load_image_bgr` (B0); medido byte-idéntico incl. EXIF/alpha |
| `.tmp` corrupción concurrente | 3 sitios, tempfile único (B0); test directo |
| `/analyze` acoplado a render+red | glifos diferidos; `/analyze` devuelve familias |
| tocar fontid reabre archivo estable | aislado en B0 con aceptación propia |
| primer server en CI (deps) | aislado a B1; B0 y el CLI no dependen de fastapi |
