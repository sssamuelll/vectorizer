# recompose como app web — diseño maestro (v2, post-junta)

**Fecha:** 2026-06-07 (DRAFT mañana; v2 misma tarde, tras junta de 7 sillas)
**Estado:** v2 — **descompuesto en tres specs A→B→C** por veredicto convergente de Stride
y Richter, aceptado por Samuel. Este documento es el **padre**: destino, stack, síntesis
de la junta, y el reparto. Cada sub-spec tiene su propio ciclo spec→plan→implementación.
**Specs hijos:** `2026-06-07-recompose-core-extraction-design.md` (A, este viernes);
B (backend FastAPI) y C (frontend React) se especifican cuando A esté mergeado.
**Specs relacionados:** `2026-06-07-fontid-fase-b-design.md` (B.1, mergeado).
**Evidencia fundante:** B.1 v0.1 aceptada (XOR producto-vs-prototipo = 0 px sobre el logo de Ale).
**Junta:** Voronov, Halberg, Serrano, Iris Tane, Richter, Stride, Vex Rune (2026-06-07, sobre el DRAFT).

---

## 0. Qué decidió el usuario (brainstorming + junta, esta sesión)

1. **El core es resolver empates a ojo** — el chooser, no validar el auto, no las escotillas.
2. **El software debe ser un programa con interfaz en el navegador, "all the way"** — no un
   CLI que abre un popup. El chooser es la primera pantalla de una app web.
3. **App completa ya** — el flujo entero en el navegador: subir → analizar → resolver
   fuentes → preview → descargar. El logo NO entra por CLI.
4. **Stack:** React + Vite + TypeScript + CSS puro (frontend); Python con **FastAPI**
   (backend); contrato **Pydantic ↔ TypeScript**.
5. **Frontera del flujo: happy path puro** — sin editor de regiones, sin `--verify`.
6. **Entrega faseada en tres specs A→B→C** (decisión post-junta) — el destino (app completa)
   no cambia; se fasea el *cómo se entrega*, no el *producto*. Spec A (core refactor) shippea
   primero, sin tocar JS, blindando la aceptación 0px antes de que el frontend la arriesgue.

## 1. Encuadre — qué supersede y qué rescata del §10 de B.1

Supersede el **chooser-popup** sobre `http.server` del §10 de B.1: ya no es un popup que
bloquea el CLI, es una app web frontend+backend.

**Rescata** (lo que la junta de B.1 ya pagó): los cortes UX de Iris (overlay magenta sobre
original neutro — el único view que destapó la 'e barrigona'; original como ancla; candidatas
de la banda Δ<0.03, máx 4; confirm atómico; "otra familia"); el threat model de Serrano
(loopback, material de cliente); la resolución de la Condición 3 (contrato).

**Retira:** las invariantes de `ThreadingHTTPServer`/`shutdown()` cross-hilo de Halberg
(las reemplaza FastAPI/uvicorn) y el timeout de 5 min como backstop (era de un popup).

## 2. El destino — arquitectura (tres piezas, un solo core)

```
vectorizer/
├── recompose_core.py   [Spec A] funciones compartidas extraídas de recompose.py
├── recompose.py        [Spec A] CLI replay (--font) — adelgaza a orquestador sobre el core
├── fontid.py           analyze_regions — intacto
├── vectorize.py        trace_contours (+ sigma) — intacto
├── server/             [Spec B] backend FastAPI (uvicorn 127.0.0.1)
│   ├── app.py            endpoints + lock OCR + token + temp store
│   └── models.py         contrato (Pydantic)
└── web/                [Spec C] Vite + React + TS + CSS puro
    └── src/{App.tsx, components/, api.ts, types.ts, *.css}
```

**Regla de oro (refinada por Vex):** el core no se duplica, **y el core es solo lo que el
backend importa**. Las funciones que solo el CLI toca (parseo de la sintaxis `--font`) NO son
core — son CLI. Mover por simetría estética infla la superficie compartida. Detalle en Spec A.

## 3. La descomposición A → B → C

| Spec | Entregable | Independiente de | Aceptación propia | Ship |
|---|---|---|---|---|
| **A** | `recompose_core.py` extraído; CLI adelgazado; AST de imports extendido | nada (prerrequisito de B) | **el CLI sigue dando 0px** contra `logo_ale_perfecto.svg` | vie 12-jun |
| **B** | backend FastAPI: `/api/analyze` + `/api/compose`; contrato Pydantic; lock OCR; token; temp store con ciclo de vida | A | `/compose` por `TestClient` da **SVG byte-idéntico** al CLI | vie 19-jun |
| **C** | frontend React: upload → overlay magenta por región → confirm atómico → descarga | B (contrato) | Samuel maneja la app sobre el logo de Ale → SVG idéntico; **el ojo re-juzga el render en el navegador** (§5 ④) | vie 26-jun |

Orden estricto A→B→C, tres merges. Si C duele, A y B ya son útiles en producción.

## 4. El contrato (Condición 3)

El frontend React es el "primer consumidor externo" que B.1 esperaba para congelar el contrato.
`server/models.py` (Pydantic) es la fuente del lado servidor; el lado TS lo consume. **Decisión
generado-vs-a-mano diferida a Spec B/C**: Vex midió el contrato real (≈6 tipos planos) y argumenta
que `types.ts` a mano (≈40 líneas) puede valer más que la toolchain `openapi-typescript` + gate CI.
Richter advierte que si se genera, falta el eslabón que el draft escondió: **TypeScript hereda del
DTO, no de la dataclass `RegionAnalysis`**, y el mapeo dataclass→DTO es manual — necesita un **test
de isomorfismo de campos**, no buena fe. Sea generado o a mano, ese test de isomorfismo es la garantía
real, no la generación. `opsz` sigue fuera del contrato hasta implementarse.

## 5. Síntesis de la junta — convergencias y disposición

Ordenadas por número de sillas que tocaron el mismo nervio (la convergencia *es* la señal).

**① El oráculo de render — 4 sillas (Voronov, Halberg, Serrano, Richter). BLOCKER de aceptación.**
La aceptación 0px de B.1 **nunca fue sobre el SVG — fue sobre su render con resvg**. El web path
renderiza con el navegador (Blink), que no rasteriza igual (anti-aliasing, subpíxel, fill-rule). Y
la evidencia de la 'e barrigona' (N=2) se ganó en un PNG de resvg; *"la evidencia perceptual está
indexada a su oráculo"* (Richter) — no se hereda gratis a Blink. Antes incluso: el raster por multipart
puede no ser byte-idéntico al del disco (EXIF/gamma/recompresión) y el Otsu es sensible al histograma
(Voronov, Halberg). **Disposición:** la aceptación se parte en dos: **(a)** identidad del *texto SVG*
(testeable, real, se mantiene como gate de A y B) y **(b)** paridad de *píxel* — NO se reclama
cross-rasterizador; el ojo **re-juzga en el navegador** (es la "regresión de juicio" de B.1, ahora
con dueño: Spec C). Más una invariante nueva: **hash del raster CLI-disco == hash del raster en temp**
(Spec B), o la byte-identidad no se hereda.

**② Ciclo de vida del `imageId`/temp store — 3 sillas (Voronov, Halberg, Serrano). BLOCKER (Spec B).**
"Una imagen a la vez" + `imageId` explícito se contradicen: si hay imageId, el store es un **mapa**,
no un singleton (dos pestañas → la segunda pisa el raster de la primera → `/compose` compone contra
la imagen equivocada, silencioso). **Disposición (Spec B):** store = mapa con TTL/GC + borrado en
shutdown; guardar la `RegionAnalysis` **junto** al raster (no recomputar — el OCR podría re-segmentar);
definir el comportamiento ante `imageId` expirado. Y un BLOCKER de corrupción real ya confesado en el
código: **`fontid.py:253` usa un solo `.tmp` por familia** → dos descargas concurrentes de la misma
fuente truncan el TTF en caché. El web lo activa por estructura → tempfile único por escritura (Spec B,
condición de merge).

**③ La política no tiene dueño — 2 sillas (Voronov, Serrano). Disposición de diseño (B y C).**
`main()` no es plomería delgada: es la sede de la ley (costura, gate de empate, conteo glifos≠chars→
vectoriza). El §5 del draft disolvía esa máquina de estados sin reasignarla → terminaba recomputada
en TypeScript. **Disposición:** el **backend computa los hechos** (`tie`, costura, elegibilidad,
qué regiones son empate vs líder-claro); el **frontend los muestra y gate-ea, no los re-deriva**. La
costura (`seam_decision`) corre una sola vez en `/analyze`.

**④ Network en el camino caliente — 2 sillas (Halberg, Serrano). HIGH (Spec B).** `download_family_weights`
golpea GF antes del disco (deuda B.1 §13); `/api/analyze` cold-cache puede tardar decenas de segundos,
con `ThreadPoolExecutor(8)` anidado por petición y sin backpressure ni timeout de request. **Disposición
(Spec B):** el lock envuelve **solo** `recognize_cv2_sync`, nunca la red; timeout de request; sin pools
anidados sin límite. (Halberg verificó en vivo: winocr+uvicorn threadpool **no** racea en esta máquina —
el lock se mantiene por prudencia single-user, no por corrupción demostrada; documentarlo así.)

**⑤ El contrato "de forma única" son 4 saltos con 1 gate — Richter, Vex, Serrano.** Ver §4. Disposición:
test de isomorfismo dataclass↔DTO en Spec B; decidir generado-vs-a-mano con el tamaño real sobre la mesa.

**⑥ Iris — "lista de principios disfrazada de layout".** El ASCII del draft traiciona sus propios cortes
del §10: centra el ancla (juró riel izquierdo), **miniaturiza el overlay** (el juicio debe pasar sobre el
original grande, no en cards → deriva a "¿cuál te gusta?" en vez de "¿cuál calza?"), pesa igual la región
resuelta que la disputada, deja el botón de descarga muerto dominando la jerarquía, y **filtra el score por
el asterisco `cand B*`**. Tres redibujos (Spec C): descarga al final del riel; "otra familia" como escape
de texto, no cuarta card; matar el asterisco. *"Redibujar, no rediseñar"* — la arquitectura es sólida.

**Cortes de grasa (Vex + Stride, para B/C):** `/api/families` de búsqueda → un `<input>` de texto +
`/api/candidate` (la soberanía Nanum Myeongjo NO necesita búsqueda; `resolve_ttf` baja cualquier familia
on-demand). `/api/image/{imageId}` → `URL.createObjectURL(file)` en el cliente (el navegador ya tiene el
raster; no servir material de cliente de vuelta). Precomputar las ≤4 candidatas en `/analyze` (sin lazy
`/candidate` en v1). Sin preview compuesto aparte (el overlay magenta SVG-nativo **es** el juicio).
→ de 5 endpoints a ≈3, dos componentes menos, una rama del threat model menos.

## 6. Specs B y C — diseño diferido (la junta ya lo pagó)

Para que B y C no re-paguen la junta:
- **Spec B (backend):** endpoints `/api/analyze` + `/api/compose` (precompute candidatas); `server/models.py`
  Pydantic + test de isomorfismo dataclass↔DTO; lock solo-OCR + timeout; token de sesión (mecanismo de
  entrega a definir — Serrano H4: incoherente con frontend estático si no se resuelve); temp store = mapa
  con TTL/GC + RegionAnalysis guardada; arreglar `.tmp` de la caché TTF; contrato de errores HTTP
  (`FontKeyError`→status, en el OpenAPI); invariante hash-del-raster; bind 127.0.0.1. Aceptación: `/compose`
  por `TestClient` byte-idéntico al CLI.
- **Spec C (frontend):** upload (`createObjectURL` para el ancla); overlay magenta **sobre el ancla grande**,
  no miniaturizado; confirm atómico; descarga al final del riel; "otra familia" como input de texto;
  sin asterisco de líder; `types.ts` (generado o a mano + isomorfismo). Aceptación: Samuel maneja la app →
  SVG idéntico + **re-juzga el render en el navegador** (cubre la regresión de juicio).

## 7. No-goals (v1, todas las fases)

Editor de regiones · `--verify` · multi-imagen (v1 = una a la vez) · multicolor/inpainting ·
búsqueda `/api/families` · preview compuesto aparte · identificar la fuente "correcta" · kerning propio ·
persistencia/DB · auth real (app local single-user) · paridad de píxel cross-rasterizador (§5 ①).

## 8. Riesgos vivos

| riesgo | disposición |
|---|---|
| el web path NO da el píxel del CLI (oráculo de render distinto) | aceptación partida texto-vs-render; el ojo re-juzga en Blink (Spec C) |
| raster no byte-idéntico tras multipart | invariante hash-del-raster (Spec B) |
| `imageId` singleton vs mapa → compose contra imagen equivocada | mapa con TTL/GC + RegionAnalysis guardada (Spec B) |
| `.tmp` compartido de la caché TTF → corrupción concurrente | tempfile único por escritura (Spec B, condición de merge) |
| política de empate duplicada en TS | backend computa hechos, frontend muestra/gate-ea (B y C) |
| toolchain JS (primer JS del repo) | aislado a Spec C; A y B no tocan JS |
| network en camino caliente de `/analyze` | lock solo-OCR + timeout (Spec B) |
| contrato: 4 saltos, 1 gate | test de isomorfismo dataclass↔DTO (Spec B) |
```
