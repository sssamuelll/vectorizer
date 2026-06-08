# Spec B0 — Core Hardening — Plan de Implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hacer los tres cambios de core/lib que el server (B1) necesita y que tienen aceptación
**CLI-byte-idéntica** — extraer `resolve_choices` a `recompose_core`, `.tmp` único por escritura en
`fontid` (3 sitios), y `load_image_bgr_from_bytes` compartiendo el decode — **sin cambiar una salida
observable del CLI**.

**Architecture:** Refactor + fix concurrencia, green-to-green. Los 100 tests existentes son la red de
seguridad; cada cambio es CLI-invisible (gate: el logo de Ale sigue byte-idéntico). Tres cambios
independientes en tres archivos distintos (`recompose_core`/`recompose`, `fontid`, `vectorize`), más
el gate de aceptación.

**Tech Stack:** Python 3.14, pytest, cv2, numpy. Sin deps nuevas, sin server, sin JS.

**Spec:** `docs/superpowers/specs/2026-06-08-recompose-core-hardening-design.md`
**Padre B:** `docs/superpowers/specs/2026-06-08-recompose-backend-design.md`

---

## Estructura de archivos

| archivo | cambio | responsabilidad |
|---|---|---|
| `recompose_core.py` | +`ChoiceResolution` +`resolve_choices` | dueño único de la política empate>líder>error |
| `recompose.py` | `main()` usa `resolve_choices` | orquestador CLI (presentación) |
| `fontid.py` | +`_atomic_write`, 3 sitios `.tmp` | descarga atómica segura bajo concurrencia |
| `vectorize.py` | +`_bgr_from_decoded` +`load_image_bgr_from_bytes` | decode compartido path/bytes |
| `tests/test_recompose_core.py` | +tests `resolve_choices` | |
| `tests/test_fontid.py` o nuevo | +tests `_atomic_write` | |
| `tests/test_vectorize.py` | +tests decode-desde-bytes | |

---

## Task 1: `resolve_choices` + `ChoiceResolution` en `recompose_core` (junta ①)

**Files:**
- Modify: `recompose_core.py` (añadir al final, tras `compose_hybrid_svg`)
- Test: `tests/test_recompose_core.py`

`main()` NO se toca en esta tarea (es la Task 2). Aquí se añade la función pura + sus tests.

- [ ] **Step 1: Escribir los tests (fallan: no existe)**

Añadir a `tests/test_recompose_core.py`:

```python
# ── resolve_choices: la política empate>líder>error (extraída de main) ──

def test_resolve_choices_lider_sin_empate_rellena():
    r = _region(text="abc", classification="type",
                ranking=_rank(("Lora", 400, 0.80, False), ("PT Serif", 400, 0.60, False)))
    res = recompose_core.resolve_choices([r], {})
    assert res.recomp_idx == [0]
    assert res.effective == {0: ("Lora", 400)}    # líder rellenado
    assert res.pendientes == [] and res.ignoradas == []


def test_resolve_choices_empate_queda_pendiente():
    r = _region(text="mente", classification="type",
                ranking=_rank(("Cormorant Garamond", 500, 0.753, False),
                              ("Libre Baskerville", 400, 0.747, True)))
    res = recompose_core.resolve_choices([r], {})
    assert res.recomp_idx == [0]
    assert 0 not in res.effective                 # no se rellena el empate
    assert [i for i, _ in res.pendientes] == [0]


def test_resolve_choices_explicita_gana():
    r = _region(text="mente", classification="type",
                ranking=_rank(("Cormorant Garamond", 500, 0.753, False),
                              ("Libre Baskerville", 400, 0.747, True)))
    res = recompose_core.resolve_choices([r], {0: ("Nanum Myeongjo", 400)})
    assert res.effective == {0: ("Nanum Myeongjo", 400)}
    assert res.pendientes == []                   # con elección no hay pendiente


def test_resolve_choices_choice_sobre_handwriting_es_ignorada():
    r = _region(text="libre", classification="handwriting", score=0.2)
    res = recompose_core.resolve_choices([r], {0: ("Lora", 400)})
    assert res.recomp_idx == []                   # handwriting no recompone
    assert res.ignoradas == [0]                   # la elección queda registrada como ignorada
    assert 0 not in res.effective


def test_resolve_choices_type_sin_ranking_sin_font_no_recompone():
    r = _region(text="abc", classification="type", ranking=[])
    res = recompose_core.resolve_choices([r], {})
    assert res.recomp_idx == [] and res.pendientes == []
```

- [ ] **Step 2: Correr — fallan**

Run: `python -m pytest tests/test_recompose_core.py -k resolve_choices -q`
Expected: FAIL con `AttributeError: module 'recompose_core' has no attribute 'resolve_choices'`.

- [ ] **Step 3: Implementar en `recompose_core.py`** (al final del archivo):

```python
@dataclass
class ChoiceResolution:
    """Salida de resolve_choices — la política empate>líder>error con un solo dueño."""
    effective: dict      # {idx: (family, wght)} — explícitas + relleno de líder
    recomp_idx: list     # [idx] a recomponer
    decisions: list      # [SeamDecision] por región (para el reporte de costura)
    pendientes: list     # [(idx, region)] empate sin elección
    ignoradas: list      # [idx] choices apuntando a región NO recompuesta


def resolve_choices(regions, choices):
    """Política empate>líder>error, extraída verbatim de main() (recompose.py).
    choices: {idx: (family, wght)} EXPLÍCITAS. has_font se evalúa contra las
    explícitas (orden canónico de main), no contra el relleno. Función PURA: no
    imprime — el orquestador presenta (CLI: stderr/exit; backend: HTTP)."""
    decisions = [seam_decision(r, has_font=(i in choices))
                 for i, r in enumerate(regions)]
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
(`dataclass` y `seam_decision` ya están en el módulo — verificar, no re-importar.)

- [ ] **Step 4: Correr — pasan**

Run: `python -m pytest tests/test_recompose_core.py -k resolve_choices -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add recompose_core.py tests/test_recompose_core.py
git commit -m "feat(recompose-core): resolve_choices + ChoiceResolution (dueno de la politica)"
```

---

## Task 2: `main()` usa `resolve_choices` (byte-idéntico)

**Files:**
- Modify: `recompose.py:197-252` (el bloque de resolución + el import)

- [ ] **Step 1: Reemplazar el bloque de resolución en `main()`**

En `recompose.py`, reemplazar las líneas `205-241` (desde `decisions = [seam_decision(...` hasta el
`raise SystemExit(EXIT_EMPATE_PENDIENTE)` inclusive) por:

```python
    resolved = resolve_choices(regions, choices)
    print_seam_report(regions, resolved.decisions)

    if not resolved.recomp_idx:
        print("\nNinguna región supera la costura — nada que recomponer.")
        print("Para vectorización pura usa: python vectorize.py", args.input)
        raise SystemExit(EXIT_NADA_QUE_RECOMPONER)

    # --font sobre región que la costura no recompone: avisar, jamás tragar
    for i in resolved.ignoradas:
        d = resolved.decisions[i]
        print(f"  [WARN] --font para \"{regions[i].text}\" ignorado: "
              f"la región no se recompone ({d.reason})", file=sys.stderr)

    if resolved.pendientes:
        print("\nEmpate sin decisión (Δ<0.03) — el replay exige --font:")
        for i, r in resolved.pendientes:
            for e in r.ranking[:4]:
                marca = " (líder)" if e is r.ranking[0] else ""
                print(f'  --font "{r.text}={e.family}:{e.wght}"'
                      f'  # overlap {e.score:.3f}{marca}')
        raise SystemExit(EXIT_EMPATE_PENDIENTE)
```

Luego, en el bloque del compositor (líneas ~243-252), cambiar `choices`/`recomp_idx` por los de
`resolved`:
```python
    # compositor (cableado en el core — dueño único)
    cache_dir = Path(args.cache_dir)
    try:
        res = compose_hybrid_svg(img, regions, resolved.effective,
                                 resolved.recomp_idx, args.contour_sigma, cache_dir)
    except FontKeyError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(EXIT_FONT_KEY)
    svg_text = res.svg_text
    final_choices = {i: resolved.effective[i] for i in resolved.recomp_idx}
```
(El resto de `main()` — write, prints, preview, `print_correction_commands`, `SystemExit(0)` — queda
igual. `res` sigue siendo el `ComposeResult`.)

- [ ] **Step 2: Añadir `resolve_choices` al import de `recompose_core`**

En `recompose.py`, el import `from recompose_core import (...)` gana `resolve_choices`:
```python
from recompose_core import (COLOR_WARN_THRESHOLD, FontKeyError,
                            compose_hybrid_svg, resolve_choices, seam_decision)
```
> Nota: `recompose_core` NO está en el allowlist del AST (`ALLOWED_IMPORTS` solo vigila `fontid`/
> `vectorize`), así que este import NO requiere tocar `test_superficie_de_imports_cerrada`. `seam_decision`
> sigue importado (lo usa `resolve_choices`… no — lo usa el core internamente; `main()` ya no llama
> `seam_decision` directo tras este cambio). **Quitar `seam_decision` del import si `main()` ya no lo
> referencia** (verificar con grep: si no aparece `seam_decision(` en recompose.py fuera del import,
> quitarlo). Mantener `print_seam_report` (lo llama main).

- [ ] **Step 3: Correr la suite — verde, comportamiento idéntico**

Run: `python -m pytest tests/test_recompose.py tests/test_recompose_core.py -q`
Expected: PASS (mismos counts). Los tests de `main()` (empate→EXIT 3, líder→compose, `[WARN]`,
sin-fuente→EXIT 2) verifican que el comportamiento no cambió.

- [ ] **Step 4: Verificar que no quedan imports muertos**

Run: `python -m pyflakes recompose.py recompose_core.py`
Expected: sin salida (limpio). Si `seam_decision` quedó importado sin uso, quitarlo.

- [ ] **Step 5: Commit**

```bash
git add recompose.py
git commit -m "refactor(recompose): main() usa resolve_choices (un dueno de la politica)"
```

---

## Task 3: `.tmp` único por escritura en `fontid` (junta ④, 3 sitios)

**Files:**
- Modify: `fontid.py` (nuevo helper `_atomic_write` + 3 sitios: `download_ttf`, `fetch_metadata`,
  `download_family_weights`)
- Test: `tests/test_fontid.py` (crear si no existe) o `tests/test_recompose_core.py`

- [ ] **Step 1: Escribir los tests del helper (fallan: no existe)**

Crear/añadir en `tests/test_fontid.py`:
```python
import sys, threading
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fontid


def test_atomic_write_concurrente_no_corrompe(tmp_path):
    """8 hilos escriben el MISMO destino: contenido íntegro, sin .tmp huérfano."""
    dest = tmp_path / "fuente.bin"
    data = b"A" * 200_000          # payload grande: la escritura no es instantánea
    def writer():
        fontid._atomic_write(dest, data, validate=None)
    ts = [threading.Thread(target=writer) for _ in range(8)]
    for t in ts: t.start()
    for t in ts: t.join()
    assert dest.read_bytes() == data                 # ni truncado ni entrelazado
    assert not list(tmp_path.glob("*.tmp"))          # sin temporal huérfano


def test_atomic_write_validacion_falla_no_promueve(tmp_path):
    dest = tmp_path / "f.bin"
    ok = fontid._atomic_write(dest, b"data", validate=lambda p: False)
    assert ok is False
    assert not dest.exists()
    assert not list(tmp_path.glob("*.tmp"))
```

- [ ] **Step 2: Correr — fallan**

Run: `python -m pytest tests/test_fontid.py -q`
Expected: FAIL con `AttributeError: module 'fontid' has no attribute '_atomic_write'`.

- [ ] **Step 3: Implementar el helper + aplicarlo a los 3 sitios**

En `fontid.py`, añadir `import tempfile` al bloque de imports (si no está), y el helper (cerca de
`download_ttf`):
```python
def _atomic_write(dest, data, validate=None):
    """Promueve `data` a `dest` atómicamente vía tempfile ÚNICO en el mismo
    directorio (seguro bajo concurrencia: cada escritor tiene su propio .tmp,
    sin colisión de nombre). `validate(tmp_path)->bool`; si False, no promueve.
    Devuelve True si `dest` quedó escrito."""
    dest = Path(dest)
    with tempfile.NamedTemporaryFile(dir=str(dest.parent), suffix=".tmp",
                                     delete=False) as tf:
        tf.write(data)
        tmp = Path(tf.name)
    try:
        if validate is not None and not validate(tmp):
            return False
        os.replace(tmp, dest)
        return True
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
```

**Sitio 1 — `download_ttf` (`fontid.py:251-258`):** reemplazar el bloque del `.tmp` por:
```python
    if _atomic_write(dest, data, validate_ttf):
        return dest
    return None
```
(borra el comentario `:251-252` y las líneas `tmp = dest.with_suffix(".tmp")` … `os.replace(...)`.)

**Sitio 2 — `fetch_metadata` (`fontid.py:288-295`):** validar el JSON en memoria ANTES de promover,
luego `_atomic_write` sin validación de archivo:
```python
            raw = urllib.request.urlopen(GF_METADATA_URL, timeout=30).read()
            json.loads(raw.decode("utf-8"))     # valida; ValueError cae al except
            _atomic_write(dest, raw)
```
(elimina `tmp = dest.parent / (dest.name + ".tmp")`, `tmp.write_bytes(raw)` y el `os.replace`; el
`except (... ValueError)` ya estaba y sigue capturando el json inválido. El `tmp.unlink` del except
sobra ahora — quitarlo.)

**Sitio 3 — `download_family_weights` (`fontid.py:371-376`):** reemplazar el bloque del `.tmp` por:
```python
            if not _atomic_write(dest, data, validate_ttf):
                continue
        out.append((wght, dest))
```
(la línea `out.append((wght, dest))` ya existe DESPUÉS del `if not dest.exists()`; mantenerla — el
`_atomic_write` reemplaza solo el `tmp=…; write; validate; replace` interno.)

- [ ] **Step 4: Correr — pasan + suite verde**

Run: `python -m pytest tests/test_fontid.py -q`
Expected: PASS (2 passed).
Run: `python -m pytest tests/ -q`
Expected: 100+ passed (los existentes intactos; el `.tmp` es CLI-invisible).

- [ ] **Step 5: Commit**

```bash
git add fontid.py tests/test_fontid.py
git commit -m "fix(fontid): tempfile unico por escritura en los 3 sitios .tmp (concurrencia)"
```

---

## Task 4: `load_image_bgr_from_bytes` (decode compartido) en `vectorize` (junta ③)

**Files:**
- Modify: `vectorize.py:33-52` (extraer `_bgr_from_decoded`, añadir `load_image_bgr_from_bytes`)
- Test: `tests/test_vectorize.py`

- [ ] **Step 1: Escribir los tests (fallan: no existe `load_image_bgr_from_bytes`)**

Añadir a `tests/test_vectorize.py`:
```python
def test_load_from_bytes_igual_que_path(tmp_path):
    img = np.full((40, 60, 3), 200, np.uint8)
    img[10:20, 10:20] = (30, 60, 90)
    p = tmp_path / "x.png"
    cv2.imwrite(str(p), img)
    a = vectorize.load_image_bgr(p)
    b = vectorize.load_image_bgr_from_bytes(p.read_bytes())
    assert np.array_equal(a, b)


def test_load_from_bytes_png_alpha(tmp_path):
    """Política de alpha idéntica entre path y bytes (el caso que el draft tenía mal)."""
    bgra = np.zeros((20, 20, 4), np.uint8)
    bgra[..., :3] = (40, 80, 120)
    bgra[..., 3] = 128                     # semi-transparente → compone sobre blanco
    p = tmp_path / "a.png"
    cv2.imwrite(str(p), bgra)
    assert np.array_equal(vectorize.load_image_bgr(p),
                          vectorize.load_image_bgr_from_bytes(p.read_bytes()))
```
(Verificar que `tests/test_vectorize.py` ya importe `vectorize`, `cv2`, `numpy as np`; si no, añadir.)

- [ ] **Step 2: Correr — fallan**

Run: `python -m pytest tests/test_vectorize.py -k from_bytes -q`
Expected: FAIL con `AttributeError: module 'vectorize' has no attribute 'load_image_bgr_from_bytes'`.

- [ ] **Step 3: Refactorizar `vectorize.py:33-52`**

Reemplazar la función `load_image_bgr` por la versión que comparte el post-decode:
```python
def _bgr_from_decoded(img):
    """Política compartida alpha/bit-depth/gris sobre un array ya decodificado
    (salida de imread o imdecode con IMREAD_UNCHANGED). None si img es None."""
    if img is None:
        return None
    if img.dtype == np.uint16:                    # PNG de 16 bits → 8 bits
        img = (img // 257).astype(np.uint8)
    if img.ndim == 2:                             # escala de grises → BGR
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if img.shape[2] == 4:                         # BGRA → componer sobre blanco
        alpha = img[:, :, 3:4].astype(np.float64) / 255.0
        bgr = img[:, :, :3].astype(np.float64)
        return (bgr * alpha + 255.0 * (1.0 - alpha)).astype(np.uint8)
    return img


def load_image_bgr(image_path):
    """Carga una imagen como BGR uint8, componiendo alpha sobre blanco.
    Devuelve None si la imagen no se puede cargar (igual que cv2.imread)."""
    return _bgr_from_decoded(cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED))


def load_image_bgr_from_bytes(data):
    """Decodifica bytes (upload multipart) con la MISMA política que load_image_bgr.
    Medido byte-idéntico a load_image_bgr(path) para PNG/JPEG/EXIF/alpha
    (IMREAD_UNCHANGED ignora EXIF en imread e imdecode por igual)."""
    arr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED)
    return _bgr_from_decoded(arr)
```

- [ ] **Step 4: Correr — pasan + suite verde**

Run: `python -m pytest tests/test_vectorize.py -q`
Expected: PASS (incluidos los 2 nuevos; `load_image_bgr` sin cambio observable).
Run: `python -m pytest tests/ -q`
Expected: 100+ passed.

- [ ] **Step 5: Commit**

```bash
git add vectorize.py tests/test_vectorize.py
git commit -m "feat(vectorize): load_image_bgr_from_bytes (decode compartido path/bytes)"
```

---

## Task 5: Gate de aceptación — el CLI sigue byte-idéntico (0px)

**Files:** ninguno (verificación manual; el logo de Ale vive en `C:\Users\simon\Desktop\Ale\`).

Gate de merge de B0: los tres cambios son CLI-invisibles.

- [ ] **Step 1: Generar el SVG con el CLI**

Run (PowerShell):
```powershell
python recompose.py "C:\Users\simon\Desktop\Ale\logo_ale.jpeg" `
  -o "$env:TEMP\ale_b0.svg" `
  --font "mente=Nanum Myeongjo:400" `
  --font "INTEGRATIVE PSYCHOLOGY=STIX Two Text:600" `
  --contour-sigma 2
```
Expected: exit 0, escribe `ale_b0.svg`, stdout con la costura + `[OK]`.

- [ ] **Step 2: Byte-comparar contra `logo_ale_v01.svg`**

Run (PowerShell):
```powershell
if ((Get-FileHash "$env:TEMP\ale_b0.svg").Hash -eq `
    (Get-FileHash "C:\Users\simon\Desktop\Ale\logo_ale_v01.svg").Hash) {
  "BYTE-IDENTICO - gate B0 verde"
} else { "DIVERGE - revisar (resolve_choices cambio una salida)" }
```
Expected: `BYTE-IDENTICO - gate B0 verde`.

- [ ] **Step 3: Suite completa + pyflakes**

Run: `python -m pytest tests/ -q` → 100+ passed.
Run: `python -m pyflakes recompose.py recompose_core.py fontid.py vectorize.py` → limpio.
Si todo verde, B0 está listo para PR (rama `recompose-core-hardening` → main).

---

## Self-Review (hecho al escribir el plan)

- **Cobertura del spec:** §2 `resolve_choices` → Task 1+2. §3 `.tmp` 3 sitios → Task 3. §4
  decode-desde-bytes → Task 4. §5 aceptación byte-idéntica → Task 5 (+ Tasks 2/3/4 mantienen la suite).
  §6 no-goals (cero server/deps/cambio CLI) → respetados.
- **Placeholders:** ninguno. Todo el código nuevo (`resolve_choices`, `_atomic_write`,
  `_bgr_from_decoded`/`load_image_bgr_from_bytes`) y los reemplazos de `main()`/los 3 sitios están
  completos con líneas exactas.
- **Consistencia de tipos:** `resolve_choices(regions, choices) -> ChoiceResolution` con campos
  `effective/recomp_idx/decisions/pendientes/ignoradas`; `main()` (Task 2) los consume con esos
  nombres. `_atomic_write(dest, data, validate=None) -> bool` usado en los 3 sitios con la firma
  correcta (`validate_ttf` o `None`). `load_image_bgr_from_bytes(data)` y `_bgr_from_decoded(img)`
  consistentes con `load_image_bgr`.
- **AST:** Task 2 NO toca `test_superficie_de_imports_cerrada` (recompose_core no está en el allowlist).
