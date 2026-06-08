# Spec C1a — Frontend, esqueleto caminante (happy path end-to-end)

Fecha: 2026-06-08 (rev. tras junta de 7 sillas + spikes sobre logos reales)
Arco: recompose como app web (A → B → C). C se parte en C0 (backend overlay, MERGEADO PR #6) + **C1 (frontend)**. C1 se parte en **C1a (este spec, esqueleto)** + C1b (relleno rico).
Depende de: el backend completo (B1 `/api/analyze`, `/api/compose`; C0 `/api/overlay`), el prototipo de diseño del equipo.

## 0. Evidencia que moldeó esta revisión

Dos logos reales por el pipeline (`analyze_regions` + `_decision`):
- **Logo de Ale** (1507×1044): 2 regiones, ambas `tie` (bandas 2 y 4). El caso de aceptación.
- **Logo de Maria** (761×640): **0 regiones**, `colorWarning` true (13 colores > umbral 12). Símbolo puro, sin texto.

La junta señaló (convergente, 3-5 sillas por hallazgo) que un "happy path active sobre un solo input" se rompe en los inputs reales. Maria lo prueba: el caso **vacío + colorWarning** no es un edge diferible, es un logo de cliente cualquiera. Por eso C1a **define el routing post-analyze para las cuatro `decision`s y el vacío**, hace el overlay **active-only**, y endurece el invariante de coordenadas, el modelo de error y la integridad async. Las pantallas *ricas* (Leader/NoFont/Vectorized con su UI propia), el banner de color visible, "otra familia", y recomponer el logo entero a la vista siguen en C1b.

## 1. Alcance

C1a entrega el happy path drivable contra el backend real: subir → analizar → **(routing por la forma del análisis)** → resolver cada empate por el overlay magenta fiel de la región **activa** → componer → descargar. Front-loadea el riesgo real (registro de coordenadas overlay↔raster, integridad async, la regresión de juicio en Blink).

**Dentro de C1a:**
- Subir (Dropzone → `createObjectURL` como ancla).
- Analizar (`POST /api/analyze`).
- **Routing post-analyze** (§4): vacío/nada-recomponible → EmptyState; con empates → choosing; recomponible-sin-empates → choosing ya completo.
- La superficie de juicio **active-only**: ancla (imagen subida) + overlay magenta de la región activa desde `/api/overlay`.
- El riel: tracker de flujo + lista de regiones con **badge para las 4 decisiones** + contador + gate de descarga.
- Componer (`POST /api/compose`) y descargar el SVG (inyectado, re-juzgado en Blink).
- EmptyState (sin texto que recomponer).
- Manejo de error **determinista** (§5).

**Fuera de C1a (→ C1b):** las pantallas ricas de región (Leader confirmable, NoFont con búsqueda manual, Vectorized con nota), recomponer el logo entero a la vista (todos los overlays confirmados simultáneos), la escotilla "otra familia" (input + overlay lazy + 422), el banner visible de color, los paneles de error ricos (mapa `ERRORS` 415/404/422/503), la textura `#scanRough` del ancla, servir el build desde FastAPI, y el pulido.

## 2. Stack y estructura

React + Vite + TypeScript + **CSS puro**. Estado con `useReducer`. Tests con **Vitest + React Testing Library**. La app vive en `web/`, habla con `http://127.0.0.1:8000` (CORS a :5173 ya en B1).

```
web/
  index.html  vite.config.ts  tsconfig.json  package.json
  src/
    main.tsx                 montaje en #root
    App.tsx                  shell (topbar + riel + main) + host de la máquina de estados
    api/
      types.ts               espejo a mano de server/models.py (RegionDTO = UNIÓN DISCRIMINADA sobre decision)
      client.ts              analyze(file) / compose(req) / overlay(req); parseo de {detail:{error}} → ApiError{status,error}
    state/
      useApp.ts              reducer (export nombrado, puro) + el hook (ata reducer + efectos)
    components/
      Rail.tsx               FlowTracker + RegionList (badge para las 4 decisiones) + contador + gate
      ChooseScreen.tsx       host de la superficie de juicio (activeRegion tie → rail+overlay; sin tie activo → ancla + "listo")
      Anchor.tsx             la imagen subida + la capa SVG magenta de la región ACTIVA, registrada a coordenadas
      CandidateRail.tsx      tarjetas (familia+peso en sans neutra; hover arma overlay desde cache; clic elige)
      Dropzone.tsx  Analyzing.tsx  EmptyState.tsx  ComposeScreen.tsx
    styles.css               port del prototipo, recortado a las pantallas del esqueleto
  tests/                     Vitest: client, reducer, anchor, contrato (recortado)
```

`reducer.ts` se pliega dentro de `useApp.ts` como export nombrado (un solo consumidor, testeable igual) — no se construye el seam de C1b por adelantado.

## 3. La superficie de juicio (`Anchor.tsx`) — active-only, registrada a coordenadas

El ancla es **la imagen subida, una sola vez** (el logo completo). Encima, una capa SVG que pinta **solo la región activa** (su candidata armada en hover, o su candidata confirmada si está elegida). Las demás regiones quedan como el original. Recomponer el logo entero a la vista (todos los overlays confirmados) es C1b.

### El invariante de coordenadas (reescrito tras la junta)

La junta corrigió el invariante: el supuesto "el `<img>` muestra los bytes subidos tal cual" es **falso** — el backend compone alpha sobre blanco y baja 16-bit (`_bgr_from_decoded`), así que el raster *visual* mostrado puede diferir del analizado. Lo que **sí** se conserva (sin resampleo ni crop) son las **dimensiones**. El invariante real:

> **`img.naturalWidth/Height === analysis.width/height`** (las dimensiones post-`_bgr_from_decoded`). La geometría de `/api/overlay` está en ese marco de píxeles entero.

Para que la capa SVG caiga sobre el píxel correcto:
- **Una sola caja compartida.** Un contenedor posicionado; dentro, `<img display:block; width:100%; height:auto>` (su aspecto intrínseco define la caja), y `<svg position:absolute; inset:0; width:100%; height:100%>` del **mismo** contenedor, con `viewBox="0 0 {analysis.width} {analysis.height}"` y `preserveAspectRatio="xMidYMid meet"`. Ambas capas escalan por el mismo factor y comparten centro → los glifos caen sobre su píxel a cualquier ancho y devicePixelRatio.
- **El CSS porteado NO debe** poner `max-height`, `object-fit` (distinto de fill), `border`/`padding` ni constraint de altura sobre el `<img>` del ancla que diverja su caja del aspecto W:H. (Riesgo concreto: un `max-height` arrastrado del prototipo desalinea el overlay en silencio.)
- **Fondo blanco** detrás del `<img>` del ancla, para que los píxeles transparentes (PNG RGBA) lean blanco, igual que el composite alpha-sobre-blanco del backend.
- **EXIF:** `image-orientation: none` en el `<img>` — el backend decodifica con `cv2.IMREAD_UNCHANGED` (ignora EXIF), así que el bitmap crudo calza. El test RTL solo verifica que la propiedad está puesta (jsdom no rasteriza); la alineación real bajo rotación se verifica con un **spike manual sobre un JPEG rotado EXIF real** (parte de la aceptación, §6), no solo el check de jsdom.

"Mantener para ver original" alterna la visibilidad de la capa SVG (mecanismo exacto fijado por el test, §6). El magenta lo pone el front (`var(--magenta)`); del backend solo viaja geometría.

## 4. Datos, máquina de estados y cliente

### Tipos (`types.ts`, a mano, unión discriminada + test de contrato)

`RegionDTO` es una **unión discriminada sobre `decision`** (no un producto con opcionales) — así el type system fuerza la correlación que el backend garantiza off-wire, y `region.candidates` solo es accesible tras estrechar `decision==="tie"`:

```ts
type Choice = { family: string; wght: number };
type RankEntry = { family: string; wght: number; score: number; tie: boolean }; // score/tie NO se muestran (regla 5)
type RegionBase = { index: number; bbox: [number, number, number, number];
                    text: string; classification: string; classScore: number };
type Region =
  | (RegionBase & { decision: "tie";        candidates: RankEntry[] })
  | (RegionBase & { decision: "leader";     chosen: Choice })
  | (RegionBase & { decision: "no_font";    reason: string })
  | (RegionBase & { decision: "vectorized"; reason: string });
type AnalyzeResponse = { imageId: string; width: number; height: number;
                         colorWarning: string | null; regions: Region[] };
type GlyphPath = { d: string; transform: string };
type OverlayResponse = { glyphs: GlyphPath[] };
type ComposeResponse = { svg: string; provenance: string[]; ignoradas: { index: number; text: string }[] };
```

### Máquina de estados (`useApp.ts`, reducer puro)

- **Fases:** `idle` → `analyzing` → (`choosing` | `empty`) → `composing` → `done`, más `error`.
- **Estado:** `{ phase, file: File|null, objectURL: string|null, analysis: AnalyzeResponse|null, choices: Record<number, Choice>, activeRegion: number|null, armed: Choice|null, overlayCache: Map<string, GlyphPath[]>, result: ComposeResponse|null, error: ApiError|null, reqSeq: number }`.
- **Clave de cache:** `` `${imageId}|${regionIndex}|${family}|${wght}` `` — incluye `imageId` para que una respuesta tardía de un logo previo no envenene el cache del actual. `RESET`/nuevo `ANALYZED` vacían el cache.
- **Routing post-analyze (`ANALYZED(resp)`):** sea `recomponible = regions.filter(decision ∈ {tie, leader})`.
  - `recomponible` vacío (incluye 0 regiones, o todo `no_font`/`vectorized`) → `phase: "empty"`.
  - hay alguna `tie` → `phase: "choosing"`, `activeRegion = ` primera `tie`.
  - recomponible sin ties (todo `leader`) → `phase: "choosing"`, `activeRegion = null` (gate ya completo; ChooseScreen muestra ancla + "listo para descargar").
  - Si `resp.colorWarning` no es null → `console.warn(resp.colorWarning)` (el banner visible es C1b; no se traga en silencio).
- **El gate, enunciado general** (para que C1b lo extienda sin reescribirlo): `requiereDecision(r) = (r.decision === "tie")` en C1a; `complete = regions.filter(requiereDecision).every(r => r.index in choices)`. Vacuosamente `true` cuando no hay ties. Descarga habilitada ⇔ `complete && phase==="choosing"`.
- **Invariante de cursor:** `armed` solo es significativo con `activeRegion` puesto. `SET_ACTIVE(idx)` **limpia `armed`** (no hay `armed!=null && activeRegion==null`). `armed` es la candidata en hover de la región activa.
- **Acciones:** `UPLOAD(file)`, `ANALYZING`, `ANALYZED(resp)`, `SET_ACTIVE(idx)`, `ARM(choice|null)`, `CHOOSE(idx, choice)`, `OVERLAY_FETCHED(key, glyphs, imageId)`, `COMPOSING`, `COMPOSED(resp)`, `FAIL(apiError, origin)`, `RESET`. `CHOOSE` avanza `activeRegion` a la siguiente `tie` sin elección (o `null` si no quedan).
- **Guardias de re-entrada:** `UPLOAD` se ignora si `phase==="analyzing"`; la descarga se ignora si `phase==="composing"` (el botón se deshabilita sincrónico por fase). `reqSeq` se incrementa en `UPLOAD`/`RESET`; `ANALYZED`/`OVERLAY_FETCHED`/`COMPOSED` que lleguen con un `imageId`/seq que ya no es el actual se **descartan** (no mutan estado).

### Efectos (en `useApp.ts`)

- `UPLOAD` → revoca el `objectURL` previo, crea uno nuevo, `analyze(file)` → `ANALYZED` o `FAIL(e,"analyze")`.
- `SET_ACTIVE(idx)` de una `tie` → **prefetch** de sus ≤4 candidatas (`overlay({imageId, regionIndex:idx, family, wght})`) al cache si faltan. El hover (`ARM`) lee el cache; **si falta (prefetch en vuelo), el overlay simplemente no se pinta aún** (el original se ve), y aparece cuando el fetch aterriza si sigue armada — sin spinner ni error, pero **definido** (no "instantáneo" a ciegas). Un fallo de `overlay` (p.ej. 422 raro) es **local**: esa candidata no previsualiza, el usuario elige otra; **no entra a `phase:error`**.
- Descargar → `compose({ imageId, choices: {"<idx>": choice} solo de empates })` → `COMPOSED` o `FAIL(e,"compose")`. **No se manda `contourSigma`** (default 2.0 del server). Los `leader` los rellena `resolve_choices` server-side; `no_font`/`vectorized` no se recomponen.

### Cliente (`client.ts`)

`request()` hace `fetch` (multipart para analyze, JSON para compose/overlay). Ante no-2xx parsea `{detail:{error}}` en `ApiError { status: number; error: string }` y lo lanza (sin `pendientes` — eso es C1b). Base URL por `import.meta.env.VITE_API_BASE` (default `http://127.0.0.1:8000`).

### Componer y descargar (`ComposeScreen.tsx`)

Inyecta el SVG real de `result.svg` (`dangerouslySetInnerHTML` u objeto SVG) — **aquí ocurre la regresión de juicio: el ojo re-juzga el render de Blink**. Riesgo notado por la junta: el `<style>` del SVG inyectado trae selectores globales `.ink`/`.type`; **renderizar el SVG aislado** (en un `<iframe>`/`shadow root`/`<img src=blob>`, no inyectado crudo en el árbol de la app) para que su stylesheet no pise las clases de la app. "Descargar SVG" baja un `Blob([result.svg], {type:"image/svg+xml"})`. Muestra `provenance` (e `ignoradas`, que en el happy path de C1a debe venir **vacío** — no-vacío señalaría un bug del front, no display normal).

## 5. Manejo de error (determinista)

`FAIL(apiError, origin)` con un `origin` explícito (no "la fase previa razonable"):
- `origin==="analyze"` → `phase:error`; reintentar → `idle` (conserva `file`/`objectURL` para re-intentar el mismo archivo o re-subir).
- `origin==="compose"` → `phase:error`; reintentar → `choosing` (estado y choices preservados).
- **`status===404`** (imageId desconocido: el backend reinició y descartó la sesión) → el error ofrece **"Re-subir"** (`RESET` → idle), no un "reintentar" que haría loop contra una sesión muerta.
- `origin==="overlay"` → **NO** entra a `phase:error`; es local a la candidata (§4 efectos).

El mensaje es plano (`error.error`) en C1a; los paneles ricos con qué/por qué/qué-hacer (mapa `ERRORS`) son C1b. C1a no se rompe ante un error: lo muestra y ofrece la salida correcta (reintentar a la fase justa, o re-subir en 404).

## 6. Tests

- **`client`** (mock `fetch`): analyze/compose/overlay arman el request correcto (método, multipart vs JSON, body sin `contourSigma`); no-2xx → `ApiError{status,error}`.
- **`reducer`** (puro):
  - Routing: `ANALYZED` con 0 regiones → `empty`; con ties → `choosing` + primera tie activa; recomponible-sin-ties → `choosing` + `activeRegion=null` + `complete=true`.
  - Gate `complete`: true solo cuando toda `tie` tiene elección; `leader`/`no_font`/`vectorized` no cuentan; `CHOOSE` avanza a la siguiente tie pendiente.
  - Invariante de cursor: `SET_ACTIVE` limpia `armed`.
  - Integridad: `OVERLAY_FETCHED` con `imageId` viejo se descarta; `RESET` vacía cache y revoca objectURL; clave de cache incluye `imageId`.
  - Error: `FAIL("...","analyze")`→retry a idle; `FAIL("...","compose")`→retry a choosing; `status 404`→RESET.
- **`anchor`** (RTL): dado glyph paths mock + `width/height`, la capa SVG tiene `viewBox="0 0 W H"` + `preserveAspectRatio="xMidYMid meet"`, un `<path>` por glifo con su `d`/`transform` y `fill` magenta; **solo la región activa** se pinta; el toggle "mantener" oculta la capa; la `<img>` lleva `image-orientation:none`.
- **`contrato`** (gated, **recortado a los campos que C1a toca**): pega a `${VITE_API_BASE}/openapi.json` vivo y verifica que los campos que C1a lee (`AnalyzeResponse.{imageId,width,height,colorWarning,regions}`, `Region.{index,bbox,text,classification,classScore,decision,candidates,chosen,reason}`, `OverlayResponse.glyphs`, `GlyphPath.{d,transform}`, `ComposeResponse.{svg,provenance,ignoradas}`) y escribe (`OverlayRequest`, `ComposeRequest` sin sigma) calzan con `types.ts`. Skip si el backend no responde.

**Aceptación (manual, la regresión de juicio):** Samuel corre `npm run dev` + el backend.
1. **Logo de Ale** → 2 empates; resuelve cada uno por el overlay magenta; descarga → SVG **byte-idéntico** a `logo_ale_v01.svg`; re-juzga el render en Blink.
2. **Logo de Maria** → **EmptyState** ("nada que recomponer") + el `console.warn` de color; no se rompe, no llega a una pantalla de elección vacía.
3. **Spike EXIF:** un JPEG rotado por EXIF → el overlay sigue alineado al píxel (verifica `image-orientation:none` en Blink, no solo en jsdom).

## 7. Supuestos declarados (corregidos tras la junta)

1. **`img.naturalWidth/Height === analysis.width/height`** (dimensiones post-decode; sin resampleo/crop sobreviven). *No* se asume que los bytes mostrados igualen los analizados (falso para RGBA/16-bit; por eso el fondo blanco y el invariante de dimensiones, §3).
2. **El backend puede estar caído o reiniciarse**: el primer fetch lo detecta (→ `phase:error` con retry a idle); un 404 mid-sesión → re-subir (§5).
3. **`resolve_choices` rellena los leader** server-side (verificado en B1), así que mandar solo choices de `tie` compone bien — *salvo* que no haya nada recomponible, caso que el routing manda a `empty` antes de intentar compose (§4).
4. **Active-only:** C1a pinta solo el overlay de la región activa; el cache solo necesita las candidatas de la activa. Recomponer todas a la vista es C1b.
5. **`createObjectURL` no re-encodea**; el `<img>` muestra el bitmap del archivo (con `image-orientation:none` + fondo blanco para calzar dimensiones y composite con el backend).
6. **Una imagen a la vez**; sin persistencia ni multi-sesión.

## 8. Notas de implementación

- Proceso: subagent-driven (implementer + spec review + quality review por tarea). Git safety: working tree compartido — prohibido `git checkout/switch/reset/stash` en cualquier prompt de subagente.
- Orden sugerido (Stride): scaffold+humo verde → cliente+types+contrato → reducer+routing+gate (test puro) → `Anchor` con el invariante (la pieza de riesgo, sola) → `CandidateRail`+prefetch → `Rail` con los 4 badges → `ComposeScreen`+descarga+error → aceptación manual (Ale + Maria + spike EXIF).
- `styles.css` se porta recortando los selectores de pantallas diferidas; medir used-vs-shipped antes del merge (Vex).
