# Spec B0 — core hardening para el server (diseño)

**Fecha:** 2026-06-08
**Estado:** spec hijo de `2026-06-08-recompose-backend-design.md` (padre B, §2). Primer entregable de B.
**Vetado por:** la junta de 6 sillas sobre el draft de B (no requiere junta propia).
**Aceptación dura:** el CLI sigue produciendo el **SVG byte-idéntico** de hoy (0px sobre el logo de Ale)
y los 100 tests siguen verdes. **Cero server, cero FastAPI, cero deps nuevas.**

---

## 1. Objetivo (una línea)

Hacer en el core/lib los tres cambios que el server (B1) necesita y que tienen aceptación
**CLI-byte-idéntica**, para mergearlos **antes** y aislados del primer servidor del repo: extraer la
política de elección a `recompose_core`, arreglar la corrupción concurrente del `.tmp` en `fontid`, y
compartir el decode de imagen para que el server pueda decodificar bytes idéntico al CLI.

## 2. Cambio 1 — extraer `resolve_choices` a `recompose_core` (junta ①)

**Por qué.** La gramática `empate>líder>error` vive inline en `main()` (`recompose.py:205-241`); el
predicado de empate (`len(r.ranking)>1 and r.ranking[1].tie`, :229) no está en ninguna función. Si B1
la re-transcribe en `/compose`, hay **dos dueños divergibles** y la byte-identidad no lo detecta. La
extracción da **un dueño** que `main()` Y `/compose` importan.

**Qué.** En `recompose_core.py`, función **pura** (no imprime — el orquestador presenta):

```python
@dataclass
class ChoiceResolution:
    effective: dict      # {idx: (family, wght)} — explícitas + relleno de líder
    recomp_idx: list     # [idx] a recomponer
    decisions: list      # [SeamDecision] por región (para el reporte de costura)
    pendientes: list     # [(idx, region)] empate sin elección
    ignoradas: list      # [idx] choices apuntando a región NO recompuesta

def resolve_choices(regions, choices):
    """Política empate>líder>error (extraída verbatim de main()). choices: {idx:(family,wght)}
    explícitas. has_font se evalúa contra las EXPLÍCITAS (orden canónico de main()), no contra
    el relleno. No imprime."""
    decisions = [seam_decision(r, has_font=(i in choices)) for i, r in enumerate(regions)]
    recomp_idx = [i for i, d in enumerate(decisions) if d.recompose]
    ignoradas = [i for i in choices if i not in recomp_idx]
    effective = dict(choices)
    pendientes = []
    for i in recomp_idx:
        if i in effective:
            continue
        r = regions[i]
        lider = r.ranking[0]
        empate = len(r.ranking) > 1 and r.ranking[1].tie
        if empate:
            pendientes.append((i, r))
        else:
            effective[i] = (lider.family, lider.wght)
    return ChoiceResolution(effective, recomp_idx, decisions, pendientes, ignoradas)
```
(`has_font=(i in choices)` con `choices`=explícitas resuelve el bug de orden que Serrano marcó.)

**Cómo refactoriza `main()`** (preserva el ORDEN de salida → stdout/stderr byte-idéntico):
`choices = resolve_font_choices(...)` → `res = resolve_choices(regions, choices)` →
`print_seam_report(regions, res.decisions)` → `if not res.recomp_idx: EXIT 2` →
`for i in res.ignoradas: [WARN]` → `if res.pendientes: imprime menú + EXIT 3` →
`compose_hybrid_svg(img, regions, res.effective, res.recomp_idx, sigma, cache_dir)`.
El formateo del `[WARN]` y del menú de empate se queda en `main()` (es presentación CLI).

**Superficie de import.** `recompose.py` importa `resolve_choices` de `recompose_core` (se añade al
allowlist del AST). `recompose_core` no gana imports externos.

**Aceptación.** (a) El gate byte-idéntico del logo de Ale sigue verde (mismo SVG). (b) Los tests de
`main()` existentes (empate→EXIT 3, líder→compose, `[WARN]` ignorado, sin-fuente→EXIT 2) pasan sin
cambio. (c) Test unitario nuevo de `resolve_choices` con fixtures sintéticos (empate→pendiente;
líder→effective; choice sobre handwriting→ignorada; type-sin-ranking→ni recomp). Sus tests viven en
`tests/test_recompose_core.py`.

## 3. Cambio 2 — `.tmp` único por escritura en `fontid` (junta ④, los 3 sitios)

**Por qué.** Tres sitios escriben un `.tmp` de nombre fijo por destino → dos escrituras concurrentes
del mismo destino se pisan antes del `os.replace`. La concurrencia **ya existe** (el
`ThreadPoolExecutor(8)` de `prepare_pool_weights`); el server la amplía. El comentario en
`fontid.py:251-252` ya lo confiesa.

**Qué (los tres, con su perfil real — corrección de Halberg):**
- `fontid.py:371` `download_family_weights` — **el primario operacional** (camino de `/analyze`),
  `.tmp` por-peso (`Nanum_Myeongjo_400.ttf.tmp`).
- `fontid.py:253` `download_ttf` (single weight), `.tmp` por-familia.
- `fontid.py:288` `fetch_metadata` — **global** (`metadata.json.tmp`), perfil distinto: lo comparten
  TODAS las familias.

**Cómo.** Cada escritura usa un tempfile **único** en el mismo directorio que el destino, escribe,
**valida** (TTF: `validate_ttf`; metadata: `json.loads` — cada sitio conserva su validación), y
`os.replace(tmp, dest)` (atómico). Patrón: `tempfile.NamedTemporaryFile(dir=dest.parent, suffix=".tmp",
delete=False)` → cada writer tiene su propio nombre → sin colisión. En fallo: `unlink` del tmp.

**Aceptación.** Test directo de concurrencia (sin server): N hilos que descargan la misma familia
(red mockeada para devolver bytes válidos con un pequeño retardo) → la caché final es un TTF válido,
nunca truncado/entrelazado; ningún `.tmp` huérfano. Los 100 tests siguen verdes.

## 4. Cambio 3 — decode de imagen desde bytes compartido (junta ③)

**Por qué.** El server (B1) recibe bytes por multipart; debe decodificar **idéntico** a como el CLI
lee del disco, o la byte-identidad del SVG no se hereda. `load_image_bgr` (`vectorize.py:33-52`) usa
`cv2.imread(IMREAD_UNCHANGED)` + composición alpha/16bit/gris.

**Medido (2026-06-08, esta máquina):** `cv2.imread(path, UNCHANGED)` e `cv2.imdecode(bytes, UNCHANGED)`
del mismo archivo dan **array idéntico** — incluido el logo de Ale (JPEG, hash `b56b3be7b146`) y un
JPEG con orientación EXIF=6 (ambos ignoran el EXIF; solo `imread` default lo aplica). **No hace falta
restringir a PNG.**

**Qué.** En `vectorize.py`, extraer la post-decodificación (16bit/gris/alpha) a una función
compartida y exponer un decode-desde-bytes:
```python
def _bgr_from_decoded(img):   # política alpha/bit-depth/gris (cuerpo de load_image_bgr:44-52)
    ...
def load_image_bgr(image_path):
    return _bgr_from_decoded(cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED))
def load_image_bgr_from_bytes(data):   # NUEVO — lo usa B1
    return _bgr_from_decoded(cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED))
```
`load_image_bgr(path)` queda byte-idéntico (mismo cuerpo, ahora vía la función compartida).

**Aceptación.** (a) `load_image_bgr(path)` sin cambio observable (los tests de vectorize verdes). (b)
Test nuevo: `load_image_bgr_from_bytes(open(p,"rb").read()) == load_image_bgr(p)` para el logo de Ale
(y un fixture PNG con alpha). (c) El gate byte-idéntico del CLI sigue verde.

## 5. Testing y aceptación (resumen)

- **Gate de merge:** el CLI sobre el logo de Ale → SVG byte-idéntico a `logo_ale_v01.svg` (los tres
  cambios son CLI-invisibles). 100 tests verdes (+ los nuevos de `resolve_choices`, `.tmp` concurrencia,
  decode-desde-bytes). pyflakes limpio.
- **AST de superficie:** `recompose.py` gana el import de `resolve_choices` desde `recompose_core`
  (allowlist actualizada).

## 6. No-goals de B0

Nada de server/FastAPI/JS · cero cambio de comportamiento observable del CLI · cero deps nuevas · no
se toca `analyze_regions` ni la firma de `compose_hybrid_svg` · no se restringe formato de imagen (el
decode compartido cubre PNG/JPEG/EXIF/alpha — medido).

## 7. Riesgos

| riesgo | mitigación |
|---|---|
| la extracción de `resolve_choices` cambia el orden de salida del CLI | gate byte-idéntico (stdout+SVG) — el orden se preserva explícitamente (§2) |
| el `.tmp` se arregla en 2 de 3 sitios | el spec nombra los tres con su perfil; el test cubre el primario `:371` y el global `:288` |
| `imdecode(UNCHANGED)` diverge de `imread(UNCHANGED)` en algún formato | medido idéntico para JPEG/EXIF/PNG-alpha; si aparece un formato divergente, se ancla el test a `load_image_bgr` (no a `imread` default) |
| tocar `fontid`/`vectorize` (archivos estables de A) | cambios locales con aceptación propia; B0 mergeable y reversible aislado del server |
