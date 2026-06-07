# Fase B — Recomposición (diseño v2, post-junta)

**Fecha:** 2026-06-07 (v1 mañana; v2 misma tarde, tras junta de 6 sillas)
**Estado:** v2 — alcance recortado por veredicto de Stride aceptado por Samuel:
**B.1 = replay puro (v0.1, esta semana); B.2 = sesión + chooser (diferida, con diseño ya pagado en §10).**
**Specs padre:** `2026-06-05-font-identification-design.md`, `2026-06-05-general-image-vectorizer-design.md`.
**Evidencia fundante:** prototipo manual completo (`docs/calibration/2026-06-05-logo-libre-mente.md`,
scripts en `docs/calibration/scripts/`).
**Junta v1→v2:** Voronov (pre-spec), Serrano, Richter, Halberg, Null Vale, Iris Tane, Stride.
Los hallazgos absorbidos se citan en línea; los diferidos viven en §10 para que B.2 no los re-pague.

---

## 1. Qué es el producto

Tomar un logo de **una tinta** donde el texto tipográfico duele al vectorizarlo desde
píxeles, y producir un SVG híbrido: caligrafía/gráficos vectorizados desde la imagen +
texto recompuesto desde el TTF de la fuente aproximada, colocado glifo a glifo en las
posiciones del original.

**El producto NO "recompone logos". Propone una recomposición y da superficies baratas
para corregirla.** La corrección es evento de primera clase, no fallo.

### v0.1 — el core shippable (frase de Stride)

> `recompose.py logo.jpeg -o out.svg --font "texto=Familia:wght"` — modo replay puro:
> lee regiones, recompone las de tipo, vectoriza el resto, escribe SVG + preview,
> sin navegador, determinista dado el mismo caché.

Exactamente el flujo manual del logo de Ale, productizado en un comando. El empate de
fuente se resuelve a mano con el flag hasta que la sesión interactiva (B.2) tenga su
propia evidencia.

### Qué se difiere a B.2 (corte de Stride, aceptado)

Chooser de navegador, modo sesión, degradación con timeout, `--verify` integrado
(los scripts `scratch_check/diff` siguen siendo el gate manual), `--skip-region`,
`--region` manual, `--json` público. **Se difiere scope, no estructura**: la dataclass
`RegionAnalysis` y la superficie de imports se construyen bien desde v0.1.

---

## 2. Soberanía — la regla que faltaba (Voronov), con su límite honesto (junta)

Tres autoridades de verdad: **el píxel** (vectorize), **el corpus** (fontid — un argmin
que "siempre devuelve algo"), **el ojo** (el usuario). **El ojo manda.** Evidencia N=2:
gate del spike (condición 2 = juicio visual) y Ronda 3 (Cormorant ganaba en métrica
0.780 sin empate; el ojo la rechazó por "barrigona"; ganó Nanum Myeongjo, **tercera**
en e-IoU y ausente de todos los top-5 de palabra).

La junta obligó a hacer esta regla más honesta:

- **El ojo nunca origina; ratifica o veta un menú que el argmin curó** (Null Vale).
  En v0.1 el menú ni existe: el ojo decide mirando los PNG de calibración/preview y
  dicta `--font`. La cadena `--font` es **provenance de una decisión visual, no la
  decisión** — un `--font` fabricado por un script es indistinguible de uno humano, y
  el producto no pretende distinguirlos (Null Vale, glitch 1). Por eso:
- **El replay es regresión de COSTURA, no de juicio** (Richter). Certifica compositor,
  colocación y contrato con la decisión de fuente congelada. La "regresión de juicio"
  (¿el ranking sigue proponiendo lo que el ojo aceptaría?) es una categoría distinta,
  sin cobertura en v0.1, nombrada como deuda explícita de B.2 — no un agujero
  silencioso.
- **El caso peligroso es la máquina confiada-y-equivocada** (Voronov §4): por eso toda
  corrida emite SIEMPRE el preview lado-a-lado (definido en §6) + los comandos de
  corrección por región. Corregir cuesta una re-corrida, no debugging.

---

## 3. Las tres condiciones de Fase B — resolución (ajustada en v2)

**Condición 1 — Evidencia real: CUMPLIDA.** Gate del spike + Fase A aceptada + prototipo
manual verificado (registro 0.0px, XOR 1px global).

**Condición 2 — Contradicción cross-spec: RESUELTA, alcance acotado.** El no-goal de
mixtas se levanta **solo para `recompose.py`**, **solo una tinta**; `vectorize.py`
conserva su limitación. **El tercer clasificador queda nombrado**: la costura
(qué se recompone vs qué se vectoriza) la arbitra `classify_region` con
`CLASSIFY_TYPE_CUT = 0.65`. La junta añade dos honestidades:

- **0.65 es política con evidencia N=1** (Richter): se declara **provisional, con deuda
  de calibración propia** — misma disciplina que el spec del vectorizador exige a toda
  constante de routing. No se promete banda de duda en v0.1; en compensación, **la
  costura siempre se reporta**: cada región sale en stdout con su clasificación, score
  y decisión (recompuesta / vectorizada), sin silencios (Null Vale: "la frontera más
  peligrosa era la única sin ceremonia" — ahora al menos tiene testigos).
- Cuando el router de Fase 2 exista, este es el punto único a reconciliar.

**Condición 3 — Contrato de información: FORMA DEFINIDA, CONGELAMIENTO DIFERIDO.**
Fase B firmó QUÉ necesita (la dataclass de §4) y la forma tiene **una sola fuente**
(`RegionAnalysis`). Pero la junta mató el congelamiento prematuro: **no hay segundo
consumidor del JSON** (Stride: "un contrato v1 sin consumidor es ceremonia") y el campo
reservado `opsz` tenía **dos semánticas de null indistinguibles** (Richter: ¿"no tiene
eje" o "no lo capturamos"?). Resolución: `RegionAnalysis` es **interna** en v0.1; el
`--json` de fontid sigue siendo "emisión draft"; el congelamiento a contrato v1 ocurre
cuando exista el primer consumidor externo (B.2 o tercero), y `opsz` **no entra** al
contrato hasta implementarse — sin asientos reservados con dos boletos.

---

## 4. Arquitectura de módulos (v0.1)

```
recompose.py  (nuevo, ~250-350 líneas en v0.1)
├─ orquestador CLI (replay puro)
├─ compositor SVG (scratch_perfect.py productizado)
└─ emisor de preview + comandos de corrección

fontid.py     → NUEVO ENTREGABLE: analyze_regions(img) -> list[RegionAnalysis]
vectorize.py  → NUEVO: parámetro de filtro sigma en el pipeline de contorno
```

### `analyze_regions` — entregable, no superficie existente (BLOCKER 1 de Serrano)

No existe hoy; es **parte del trabajo de Fase B** y vive en `fontid.py`:

```python
@dataclass
class RegionAnalysis:
    bbox: tuple[int, int, int, int]          # absolutas en la imagen
    text: str                                 # texto OCR
    classification: str                       # "type" | "handwriting"
    class_score: float
    glyph_boxes: list[tuple[int, int, int, int]]  # absolutas (baseline real conservada)
    ranking: list[RankEntry]                  # (family, wght, score, tie) — vacío si class != type
    scale_factor: float                       # mediana alturas crop/render del matching

def analyze_regions(img_bgr) -> list[RegionAnalysis]
```

Envuelve la tubería existente (`detect_regions` → `segment_glyphs_with_boxes` →
`classify_region` → `rank_families`); **las funciones actuales no se deprecan ni
cambian de firma** — siguen siendo la API de los tests y del CLI de fontid;
`analyze_regions` es una fachada de composición. La nota de Null Vale sobre
`scale_factor` queda registrada: su semántica está atada al pipeline de segmentación
de una tinta; si B.x lo cambia, el campo NO puede conservar el nombre con otro
significado (deuda anotada, no resuelta).

### `--contour-sigma` — punto de inyección exacto (BLOCKER 2 de Serrano)

El filtro gaussiano circular opera sobre los **puntos del contorno antes del RDP** —
eso vive **dentro** de la tubería, no en la firma pública. Mecanismo: `trace_contours`
gana parámetro `sigma=0.0` y lo **pasa a `_smooth_closed_contour`**, que aplica el
filtro circular a `pts` como primer paso (antes de `rdp_simplify`), portado de
`docs/calibration/scripts/scratch_smooth_v2.py::gauss_filter_closed`. `sigma=0` ⇒
ningún cambio de comportamiento (cero regresión para todos los llamadores actuales).
El CLI de vectorize expone `--contour-sigma` (default 0); **recompose.py SIEMPRE pasa
sigma explícito** a `trace_contours` (default propio 2.0) — nunca hereda el default de
vectorize (hallazgo 12 de Serrano: dos defaults para una función exigen que el
orquestador sea explícito).

### Superficie de import — declarada Y mecánica (Richter: "Python no tiene honor")

- de `fontid.py`: **solo** `analyze_regions`, `download_family_weights`, `CACHE_DIR_DEFAULT`.
  *(Ampliada en plan-time 2026-06-07: la regla `--font` acepta cualquier familia GF
  on-demand — §5 — y duplicar el pipeline de descarga violaría la ley Halcyon.
  Esta edición es el procedimiento de ampliación funcionando como se diseñó.)*
- de `vectorize.py`: **solo** `load_image_bgr`, `trace_contours`, `extract_stroke_color`,
  `clean_binary_mask`.
- **Enforcement mecánico**: un test unitario parsea el AST de `recompose.py` y falla si
  los imports exceden la allowlist. La frontera la cierra el CI, no la prosa.
- **`clean_binary_mask` — contradicción cross-spec resuelta** (Null Vale/Richter): el
  spec padre la prohíbe **para segmentación de glifos** ("destruye serifas/puntos por
  diseño") y eso sigue vigente. En recompose se usa **exclusivamente sobre la
  caligrafía** (las regiones de texto ya fueron enmascaradas antes de binarizar), que
  es exactamente el uso original de vectorize. Las regiones de texto JAMÁS pasan por
  ella. Así lo hizo el prototipo (`scratch_perfect.py`).

---

## 5. CLI v0.1

```
python recompose.py logo.jpeg [-o out.svg]
  --font "clave=Familia:wght"   # repetible; OBLIGATORIO para toda región type con
                                # empate (Δ<0.03) — sin chooser, el replay exige la
                                # decisión explícita; sin empate, el líder es default
  --contour-sigma F             # suavizado de caligrafía (default 2.0)
  --category / --pool / --api   # passthrough a fontid (pool de candidatas)
```

### Reglas de la clave `--font` (hallazgo 5 de Serrano — determinismo)

- **Normalización**: clave y texto OCR se comparan tras `casefold()` + colapso de
  espacios internos + strip. Match **exacto** post-normalización.
- **Índice**: la forma `--font "#2=Familia:wght"` refiere a la región nº 2 (orden de
  `analyze_regions`). El prefijo `#` desambigua de un texto OCR que sea literalmente
  un número.
- **No-match = error duro** con la lista de textos de región disponibles. Nunca
  degradación silenciosa (rompería la reproducibilidad del replay).
- **La familia puede NO estar en el ranking** (BLOCKER 3/4 de Serrano — el caso Nanum
  Myeongjo): `--font` acepta cualquier familia del corpus Google Fonts; se descarga
  on-demand con el mismo pipeline de pesos de fontid. El ojo puede elegir fuera del
  menú de la métrica — esa es la regla de soberanía hecha mecanismo.
- El `wght` es obligatorio en la cadena (sin adivinar pesos).

---

## 6. Flujo de datos v0.1

```
 1. load_image_bgr → analyze_regions(img)
 2. costura: classification "type" ∧ score≥0.65 → recomponer; resto → tinta vectorizada
    → TODA región se reporta en stdout: texto, clasificación, score, decisión
 3. resolución de fuente por región a recomponer:
    --font matchea → esa familia:peso (descarga on-demand si falta)
    sin --font y sin empate → líder del ranking
    sin --font y CON empate (Δ<0.03) → ERROR con el comando --font sugerido ya armado
 4. máscara de regiones a recomponer (pad 6px) → caligrafía: Otsu inv + morph close +
    clean_binary_mask + trace_contours(sigma=2.0 explícito)
 5. por región: TTF → SVGPathPen + BoundsPen → escala común (mediana de alturas
    glifo-original/glifo-fuente) → colocación por glifo (centro-x + fondo del bbox)
    — el emparejamiento exige conteo igual (ver §7)
 6. compone SVG: grupo .ink + grupo .type, tinta de extract_stroke_color
 7. SIEMPRE emite: out.svg + out_preview.png + comandos de corrección
```

**El preview lado-a-lado, definido** (hallazgo 13 de Serrano): `out_preview.png` =
**original raster | render del SVG** (resvg si está disponible; si no, se omite el
preview con aviso — el SVG es el entregable, el preview es la superficie de juicio),
a tamaño completo, más una banda de zoom por región recompuesta. El original SIEMPRE
presente como ancla (Iris: sin el original es "¿cuál te gusta?" en vez de "¿cuál
calza?").

**Comandos de corrección** (Iris: "provenance, no superficie de corrección"): el stdout
imprime por región recompuesta el comando de re-corrida con la familia usada y las 3
siguientes del ranking. Es el **eco sintáctico de una decisión visual** que el usuario
toma mirando el preview — la superficie es el PNG; el comando es la sintaxis.

---

## 7. Manejo de errores v0.1

| falla | comportamiento |
|---|---|
| OCR no detecta regiones | aviso + exit 2 ("nada que recomponer — para vectorización pura usa vectorize.py"); no escribe SVG |
| ninguna región supera la costura (hallazgo 7 de Serrano) | mismo tratamiento: aviso con los scores + exit 2; no escribe SVG — recompose sin recomposición no es éxito silencioso |
| región type con empate y sin --font | error con comando sugerido; exit 3 (decisión pendiente) |
| --font no matchea ninguna región | error duro + lista de claves disponibles; exit 4 |
| descarga TTF falla | 1 reintento → siguiente del ranking con [WARN] a stderr; si era --font explícito, error duro (no sustituir la decisión del ojo en silencio) |
| conteo glifos ≠ caracteres sin espacios (hallazgo 9) | la región se vectoriza + aviso con ambos conteos; degradación POR REGIÓN, todo-o-nada — el emparejamiento parcial glifo-a-glifo queda como deuda B.x documentada (la fusión vertical heurística es la causa raíz conocida) |
| imagen multicolor (count_effective_colors > umbral logo) | aviso "fuera de alcance (una tinta)" + continúa bajo responsabilidad del usuario |
| stdout | utf-8 reconfigure primera línea de main; humano legible; sin --json en v0.1 |

## 8. Testing v0.1

- **Frontera mecánica**: test AST de imports de recompose.py contra la allowlist (§4).
- **Unit**: costura (scores sintéticos → decisión + reporte), reglas de clave `--font`
  (normalización, #índice, no-match), `analyze_regions` (composición correcta de la
  tubería con un fixture sintético), colocación (asserts de registro del prototipo),
  compositor (SVG parseable, viewBox, grupos, sin ns0:), sigma=0 ⇒ output idéntico al
  actual (cero regresión en vectorize).
- **Replay determinista**: misma corrida `--font` fija + mismo caché → SVG idéntico.
  **"Determinista" significa "dado el mismo caché de TTFs"** (hallazgo 10 de Serrano):
  los TTF de Google Fonts no están pinneados por hash; el caché es el insumo. El SVG
  emite como comentario la lista familia/peso/sha256 de los TTF usados (provenance
  barata que convierte la deriva upstream en diagnosticable).
- **Red** marcada `network` (convención existente).

## 9. Aceptación v0.1 (reformulada dos veces: Voronov, luego junta)

**Replay contra el prototipo, directo** (resuelve el hallazgo 8 de Serrano — el umbral
30px vs la astilla documentada de 76px era incodificable):

> `recompose.py logo_ale.jpeg --font "mente=Nanum Myeongjo:400" --font "INTEGRATIVE
> PSYCHOLOGY=STIX Two Text:600" --contour-sigma 2` produce un SVG cuyo **render se
> compara contra el render de `logo_ale_perfecto.svg`** (no contra el JPEG): XOR binario
> con tolerancia 2px → **cero clusters ≥30px, sin excepciones**. Mismas fuentes, mismo
> sigma, mismas boxes ⇒ la comparación producto-vs-prototipo no hereda el ruido
> producto-vs-raster, y la astilla de la 'm' (presente en ambos) se cancela sola.

Más: registro por glifo (mediana ratio altura 1.000, Δcentro-x y Δbaseline 0.0px)
medido contra el original, como en calibración. Verificación con los scripts de
calibración existentes (`scratch_check/measure/diff`) — `--verify` integrado es B.2.

**Lo que esta aceptación NO demuestra, dicho sin anestesia** (Richter): que el flujo
automático proponga bien. Demuestra que el reproductor de decisiones humanas reproduce.
La validación del *juicio* (sesión, chooser, regresión de juicio) es la aceptación de
B.2, con su propia evidencia. La aceptación final de v0.1 es el juicio de Samuel sobre
la corrida.

## 10. B.2 — sesión + chooser (diferida CON el diseño ya pagado)

Para que B.2 no re-pague la junta, lo decidido queda aquí:

**Del corte de Iris (UX del chooser):**
- El render del candidato ES el click-target; seleccionar = confirmar (una región =
  un clic). Confirm global solo con ≥2 regiones empatadas, deshabilitado hasta
  completar, con "1 de 2 elegidas".
- Candidatos = **los que están dentro de la banda Δ<0.03, máximo 4** — no top-4 fijo
  ("dos rivales reales mostrados como dos vale más que dos rellenados a cuatro").
- Original como ancla SIEMPRE primero, única línea de regla; stacks apretados
  baseline-con-baseline; bandas por región full-width en secuencia, un riel izquierdo,
  jamás centrar; UI en sans neutra (cero serifs propias); score escondido por default
  (es tinta de debug que rankeó primera a la 'e' rechazada).
- **Toggle de overlay** (candidata magenta sobre original neutro) — el único view que
  expuso la barriga; el side-by-side solo está probado insuficiente (Ronda 3).
- Botón/entrada **"elegir otra familia…"** fuera del menú: el caso Nanum Myeongjo
  (la familia correcta fuera del top del ranking) debe ser resoluble DENTRO del chooser,
  no solo vía --font (BLOCKER 4 de Serrano; Richter §2.1).
- En degradación: **el PNG de opciones es la superficie; el comando --font es la
  sintaxis** — nunca imprimir el comando sin escribir los PNG.

**De Halberg (invariantes runtime, verificadas en esta máquina):**
1. `http.server.ThreadingHTTPServer` (no socketserver, no HTTPServer plano); bind
   explícito `127.0.0.1` (no `0.0.0.0`, no `localhost` dual-stack — mismatch IPv4/IPv6
   cuelga silencioso).
2. `shutdown()` jamás directo en el hilo del handler de un server no-threading.
3. El timeout de 5 min ES un `threading.Event.wait(timeout=300)` en el main que el
   handler setea; la elección cruza hilos por estructura thread-safe.
4. Hilo daemon + try/except KeyboardInterrupt con shutdown()+server_close()+exit≠0.
- **"Sin navegador disponible" es indetectable en Windows**: `webbrowser.open` devuelve
  True en SSH/headless sin que nadie vea nada (verificado: `os.startfile` asíncrono).
  El timeout es el ÚNICO backstop; imprimir la URL en stdout siempre.
- winocr↔http.server: SIN conflicto de event loop (verificado) mientras el chooser sea
  threading puro y el OCR secuencial — invariante anotada, no hecho casual.

**De Serrano (threat model HTTP):** binding loopback explícito, token/nonce en el POST,
inventario de lo servido (el logo es material de cliente — misma lógica de privacidad
que justificó `--api` opt-in). Estado de elecciones parciales en timeout: definir
confirmación atómica vs por región ANTES de implementar.

**De Richter (categorías pendientes):** "regresión de juicio" como categoría de test
distinta de la regresión de costura; canal formal para "el ojo eligió fuera del menú"
(hoy: --font; B.2: el botón de Iris).

## 11. No-goals de Fase B (v0.1 y B.2)

- Logos multicolor (inpainting) → B.x.
- `opsz` — fuera del contrato hasta implementarse (sin asientos reservados).
- Identificación de la fuente "correcta" — sigue siendo aproximación sobre corpus
  libre, con su línea fija en cada reporte.
- Kerning/letterspacing propio: el espaciado SIEMPRE viene de las posiciones originales.
- Emparejamiento parcial de glifos cuando conteos difieren (deuda B.x documentada en §7).

## 12. Riesgos vivos

| riesgo | estado |
|---|---|
| la máquina confiada-y-equivocada (caso 'e') | preview + comandos SIEMPRE; resolución plena (overlay, chooser) en B.2 |
| replay ciego a regresión de juicio | nombrado como deuda B.2; replay etiquetado "regresión de costura" |
| 0.65 con evidencia N=1 | declarado provisional con deuda de calibración; costura siempre reportada |
| `scale_factor` cambia de semántica si B.x cambia la segmentación | anotado en §4; el nombre no sobrevive a un cambio de referente |
| TTFs upstream sin pin | determinismo definido "dado el mismo caché" + sha256 en provenance |
| el corte de Stride esconde una necesidad real del chooser | si una corrida real con empate duele lo suficiente, B.2 sube de prioridad con esa evidencia |
