# Spec C0 — `POST /api/overlay` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the faithful magenta-overlay geometry through `POST /api/overlay`, reusing the exact per-region path code that `/compose` uses so the eye judges what it downloads.

**Architecture:** Extract the per-region "resolve TTF + strip spaces + glyph paths" unit from `compose_hybrid_svg` into `region_overlay_paths` in `recompose_core`, so compose and the new endpoint share one owner of the geometry. Add a sync `/api/overlay` endpoint in the existing FastAPI server that wraps that unit and returns `[{d, transform}]` in full-image coordinates. `/analyze` is untouched.

**Tech Stack:** Python, FastAPI, Pydantic, fontTools (via `region_glyph_paths`), pytest. Reuses the B1 server (`server/{app,models}.py`), the store, and the `{detail:{error}}` error envelope.

**Spec:** `docs/superpowers/specs/2026-06-08-recompose-overlay-design.md`

**Git safety (all tasks):** Subagents share the controller's working tree. Do NOT run `git checkout`, `git switch`, `git reset`, or `git stash` in any subagent prompt. Only `git add` / `git commit` of the files listed per task.

---

### Task 1: `region_overlay_paths` in `recompose_core` + refactor `compose_hybrid_svg`

**Files:**
- Modify: `recompose_core.py` (add `region_overlay_paths` just before `compose_hybrid_svg` at line 249; rewrite the per-region loop body at `recompose_core.py:260-268`)
- Test: `tests/test_recompose_core.py`

This is a pure refactor: compose's output must stay byte-identical. The existing gated compose tests guard that.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_recompose_core.py` (the file already imports `recompose_core`, `fontid`, `ET`, `pytest`, and defines `_region`, `_rank`, `_logo_sintetico`, `CACHE`, `TTF_TEST`):

```python
# ── region_overlay_paths: la unidad por región compartida con el overlay (C0) ──

def test_region_overlay_paths_reusa_resolve_y_glyph_paths(monkeypatch):
    """region_overlay_paths = resolve_ttf + (quita espacios) + region_glyph_paths.
    Offline: espía las dos dependencias y verifica el cableado y los args exactos."""
    r = _region(text="ab c", n_glyphs=3)          # 3 chars sin-espacio, 3 boxes
    visto = {}

    def fake_glyph_paths(ttf, chars, boxes, family):
        visto["ttf"], visto["chars"] = ttf, chars
        visto["boxes"], visto["family"] = boxes, family
        return [("M0Z", "matrix(1)"), ("M1Z", "matrix(2)"), ("M2Z", "matrix(3)")]

    monkeypatch.setattr(recompose_core, "resolve_ttf",
                        lambda fam, w, cd: Path("/fake/Cormorant_500.ttf"))
    monkeypatch.setattr(recompose_core, "region_glyph_paths", fake_glyph_paths)

    pairs, ttf = recompose_core.region_overlay_paths(r, "Cormorant Garamond", 500, "/cache")
    assert ttf == Path("/fake/Cormorant_500.ttf")
    assert pairs == [("M0Z", "matrix(1)"), ("M1Z", "matrix(2)"), ("M2Z", "matrix(3)")]
    assert visto["chars"] == ["a", "b", "c"]       # el espacio se quitó (política única)
    assert visto["boxes"] == r.glyph_boxes
    assert visto["family"] == "Cormorant Garamond"
    assert visto["ttf"] == Path("/fake/Cormorant_500.ttf")


@pytest.mark.skipif(not TTF_TEST.exists(), reason="TTF de caché no disponible")
def test_region_overlay_paths_identico_a_compose_type():
    """LA prueba de fidelidad: los pairs de region_overlay_paths == los paths del
    <g class='type'> que compose_hybrid_svg produce para esa región+candidata.
    El ojo (overlay) juzga exactamente lo que se descarga (compose)."""
    img = _logo_sintetico()
    r = _region(text="abc", bbox=(50, 60, 250, 115), n_glyphs=3)
    pairs, _ = recompose_core.region_overlay_paths(r, "Cormorant Garamond", 500, CACHE)
    res = recompose_core.compose_hybrid_svg(
        img, [r], {0: ("Cormorant Garamond", 500)}, [0], sigma=2.0, cache_dir=CACHE)
    root = ET.fromstring(res.svg_text)
    type_g = next(g for g in root
                  if g.tag.endswith("g") and g.get("class") == "type")
    compose_pairs = [(p.get("d"), p.get("transform")) for p in type_g]
    assert pairs == compose_pairs and len(pairs) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_recompose_core.py::test_region_overlay_paths_reusa_resolve_y_glyph_paths -v`
Expected: FAIL — `AttributeError: module 'recompose_core' has no attribute 'region_overlay_paths'`.

(The gated test is skipped if `~/.cache/vectorizer-fonts/Cormorant_Garamond_500.ttf` is absent; if present it also fails for the same reason.)

- [ ] **Step 3: Add `region_overlay_paths` and refactor the compose loop**

In `recompose_core.py`, add this function immediately before `def compose_hybrid_svg` (line 249):

```python
def region_overlay_paths(region, family, wght, cache_dir):
    """[(path_d, transform)] de UNA región con una candidata, en coords de imagen
    completa — la unidad por región que compose_hybrid_svg usa, extraída para que
    el overlay del backend (Spec C0) la reuse: el ojo juzga exactamente lo que
    /compose va a producir. Devuelve (pairs, ttf_path); compose necesita el
    ttf_path para el sha de procedencia. FontKeyError si la fuente falla."""
    ttf = resolve_ttf(family, wght, cache_dir)
    chars = [c for c in region.text if not c.isspace()]
    return region_glyph_paths(ttf, chars, region.glyph_boxes, family), ttf
```

Then replace the per-region loop body in `compose_hybrid_svg` (`recompose_core.py:260-268`). The current body is:

```python
    for i in recomp_idx:
        r = regions[i]
        family, wght = choices[i]
        ttf = resolve_ttf(family, wght, cache_dir)
        sha = hashlib.sha256(ttf.read_bytes()).hexdigest()[:16]
        provenance.append(f"{family}:{wght} sha256:{sha}")
        chars = [c for c in r.text if not c.isspace()]
        glyph_pairs.extend(region_glyph_paths(ttf, chars, r.glyph_boxes, family))
        mask_boxes.append(r.bbox)
```

Replace it with:

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

- [ ] **Step 4: Run tests to verify they pass + no regression**

Run: `python -m pytest tests/test_recompose_core.py -v`
Expected: PASS. The new offline test passes; the gated fidelity (`test_region_overlay_paths_identico_a_compose_type`) + existing `test_compose_hybrid_svg_region_type_estructura` pass if the TTF cache exists, else skip. **On the dev machine the cache exists (`~/.cache/vectorizer-fonts/Cormorant_Garamond_500.ttf`), so the gated fidelity test RUNS and must be GREEN — a skip there is not acceptance.** No other core test changes behavior (pure refactor).

Run the full repo suite to confirm nothing else moved:
Run: `python -m pytest -q`
Expected: all pass (same count as before + the new test; gated tests skip without the font cache).

- [ ] **Step 5: Commit**

```bash
git add recompose_core.py tests/test_recompose_core.py
git commit -m "refactor(core): extrae region_overlay_paths (dueño unico de geometria por region)" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Overlay DTOs in `server/models.py`

**Files:**
- Modify: `server/models.py` (append three models after `ErrorResponse`, line 68)
- Test: `tests/test_server.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_server.py`:

```python
def test_overlay_dtos_forma_y_extra_forbid():
    """OverlayRequest rechaza campos extra; GlyphPath/OverlayResponse hacen round-trip."""
    import pydantic
    req = models.OverlayRequest(imageId="abc", regionIndex=0, family="Lora", wght=400)
    assert req.regionIndex == 0 and req.wght == 400
    with pytest.raises(pydantic.ValidationError):
        models.OverlayRequest(imageId="abc", regionIndex=0, family="Lora",
                              wght=400, extra="no")          # extra=forbid
    resp = models.OverlayResponse(glyphs=[models.GlyphPath(d="M0Z", transform="matrix(1)")])
    back = models.OverlayResponse.model_validate_json(resp.model_dump_json())
    assert back.glyphs[0].d == "M0Z" and back.glyphs[0].transform == "matrix(1)"
```

This test needs `pytest` imported in `tests/test_server.py`. The file does not import it yet — add at the top of the file, after `import numpy as np` (line 6):

```python
import pytest
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_server.py::test_overlay_dtos_forma_y_extra_forbid -v`
Expected: FAIL — `AttributeError: module 'server.models' has no attribute 'OverlayRequest'`.

- [ ] **Step 3: Add the DTOs**

Append to `server/models.py` (after `ErrorResponse`, line 68):

```python
class OverlayRequest(BaseModel):
    """Pide la geometría de UNA candidata sobre UNA región (Spec C0). family/wght
    pueden ser cualquiera (la escotilla 'otra familia' elige fuera del menú)."""
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

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_server.py::test_overlay_dtos_forma_y_extra_forbid -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/models.py tests/test_server.py
git commit -m "feat(server): DTOs de /api/overlay (OverlayRequest/GlyphPath/OverlayResponse)" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: `POST /api/overlay` endpoint in `server/app.py`

**Files:**
- Modify: `server/app.py` (add `region_overlay_paths` to the `recompose_core` import at line 15-16; add the endpoint after `compose`, line 140)
- Test: `tests/test_server.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_server.py`. These need `xml.etree.ElementTree` and the font-cache constants — add near the top of the file, after the existing imports (line 12):

```python
import xml.etree.ElementTree as ET
CACHE = Path.home() / ".cache" / "vectorizer-fonts"
TTF_TEST = CACHE / "Cormorant_Garamond_500.ttf"
```

Then the tests:

```python
def test_overlay_envuelve_region_overlay_paths(monkeypatch):
    """El endpoint devuelve VERBATIM lo que region_overlay_paths produce. Junto al
    test de fidelidad del core (overlay-paths == compose-type), esto prueba
    transitivamente: /api/overlay == lo que /compose descarga."""
    r = _region("abc", n_glyphs=3)
    sid = srv._put(srv.Session(_dummy_raster(), [r], 100, 20))
    monkeypatch.setattr(srv, "region_overlay_paths",
                        lambda region, fam, w, cd: ([("M0Z", "matrix(1)"),
                                                     ("M1Z", "matrix(2)")], "ttf"))
    client = TestClient(srv.app)
    resp = client.post("/api/overlay", json={"imageId": sid, "regionIndex": 0,
                                             "family": "Whatever", "wght": 400})
    assert resp.status_code == 200
    assert resp.json()["glyphs"] == [{"d": "M0Z", "transform": "matrix(1)"},
                                     {"d": "M1Z", "transform": "matrix(2)"}]
    srv._clear()


def test_overlay_404_imageid_desconocido():
    client = TestClient(srv.app)
    resp = client.post("/api/overlay", json={"imageId": "noexiste", "regionIndex": 0,
                                             "family": "Lora", "wght": 400})
    assert resp.status_code == 404 and resp.json()["detail"]["error"] == "imageId desconocido"


def test_overlay_400_region_fuera_de_rango():
    r = _region("abc", n_glyphs=3)
    sid = srv._put(srv.Session(_dummy_raster(), [r], 100, 20))
    client = TestClient(srv.app)
    for idx in (-1, 5):
        resp = client.post("/api/overlay", json={"imageId": sid, "regionIndex": idx,
                                                 "family": "Lora", "wght": 400})
        assert resp.status_code == 400
    srv._clear()


def test_overlay_400_region_no_tipografica():
    """Región vectorized (handwriting) → 400: no hay texto tipográfico que pintar."""
    r = _region("libre", classification="handwriting", score=0.2)
    sid = srv._put(srv.Session(_dummy_raster(), [r], 100, 20))
    client = TestClient(srv.app)
    resp = client.post("/api/overlay", json={"imageId": sid, "regionIndex": 0,
                                             "family": "Lora", "wght": 400})
    assert resp.status_code == 400 and "tipográfic" in resp.json()["detail"]["error"]
    srv._clear()


def test_overlay_400_charcount_no_cuadra():
    """Región type pero len(chars) != len(glyph_boxes) → 400 honesto, no un 500 de
    region_glyph_paths (replica la precondición de la costura)."""
    r = _region("abcd", n_glyphs=3)          # 4 chars, 3 boxes
    sid = srv._put(srv.Session(_dummy_raster(), [r], 100, 20))
    client = TestClient(srv.app)
    resp = client.post("/api/overlay", json={"imageId": sid, "regionIndex": 0,
                                             "family": "Lora", "wght": 400})
    assert resp.status_code == 400
    srv._clear()


def test_overlay_422_fontkey(monkeypatch):
    """familia/peso no resoluble → 422 (igual que /compose ante una fuente mala)."""
    r = _region("abc", n_glyphs=3)
    sid = srv._put(srv.Session(_dummy_raster(), [r], 100, 20))
    monkeypatch.setattr(srv, "region_overlay_paths", _raise_fontkey)
    client = TestClient(srv.app)
    resp = client.post("/api/overlay", json={"imageId": sid, "regionIndex": 0,
                                             "family": "Lora", "wght": 999})
    assert resp.status_code == 422 and "999" in resp.json()["detail"]["error"]
    srv._clear()


def test_overlay_422_body_invalido():
    """Campo extra en el body → 422 de Pydantic (extra=forbid)."""
    client = TestClient(srv.app)
    resp = client.post("/api/overlay", json={"imageId": "x", "regionIndex": 0,
                                             "family": "Lora", "wght": 400, "z": 1})
    assert resp.status_code == 422


@pytest.mark.skipif(not TTF_TEST.exists(), reason="TTF de caché no disponible")
def test_overlay_identico_a_compose_e2e():
    """End-to-end servidor: /api/overlay == el <g class='type'> que compose produce
    para la misma región+candidata. La aceptación dura de §6 sobre fuente real."""
    from recompose_core import compose_hybrid_svg
    img = np.full((120, 300, 3), 255, np.uint8)
    img[60:115, 50:250] = (60, 110, 90)        # algo de tinta para la caligrafía
    r = _region("abc", n_glyphs=3)
    r = dataclasses.replace(r, bbox=(50, 60, 250, 115),
                            glyph_boxes=[(50, 60, 110, 115), (115, 60, 175, 115),
                                         (180, 60, 240, 115)])
    sid = srv._put(srv.Session(img, [r], 300, 120))
    client = TestClient(srv.app)
    resp = client.post("/api/overlay", json={"imageId": sid, "regionIndex": 0,
                                             "family": "Cormorant Garamond", "wght": 500})
    assert resp.status_code == 200
    overlay = [(g["d"], g["transform"]) for g in resp.json()["glyphs"]]
    res = compose_hybrid_svg(img, [r], {0: ("Cormorant Garamond", 500)}, [0], 2.0, CACHE)
    root = ET.fromstring(res.svg_text)
    type_g = next(g for g in root if g.tag.endswith("g") and g.get("class") == "type")
    compose_pairs = [(p.get("d"), p.get("transform")) for p in type_g]
    assert overlay == compose_pairs and len(overlay) == 3
    srv._clear()
```

Note: `_region` in `tests/test_server.py` builds `glyph_boxes` as `[(i*10, 0, i*10+8, 20) for i in range(n_glyphs)]`; the e2e test overrides bbox + glyph_boxes via `dataclasses.replace` so the synthetic boxes have real width/height for placement. `dataclasses` is already imported at the top of the file.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_server.py -k overlay -v`
Expected: all offline overlay tests go RED (none pass), but via different mechanisms because the route and the `srv.region_overlay_paths` binding do not exist yet:
- `test_overlay_envuelve_region_overlay_paths` and `test_overlay_422_fontkey` ERROR on `monkeypatch.setattr(srv, "region_overlay_paths", ...)` → `AttributeError` (the attribute appears once Step 3 adds it to the import).
- `test_overlay_404_imageid_desconocido` ERRORs with `TypeError`: a missing route returns `404 {"detail": "Not Found"}` (a string), so `resp.json()["detail"]["error"]` indexes a str. Status is 404 only by coincidence; it goes green properly once the handler sets `detail={"error": ...}`.
- `test_overlay_400_*` and `test_overlay_422_body_invalido` fail on status mismatch (missing route → 404).
The gated `test_overlay_identico_a_compose_e2e` RUNS if the font cache exists (then it must go GREEN after Step 3), else skips.

- [ ] **Step 3: Implement the endpoint**

In `server/app.py`, add `region_overlay_paths` to the `recompose_core` import (currently lines 15-16):

```python
from recompose_core import (COLOR_WARN_THRESHOLD, FontKeyError, compose_hybrid_svg,
                            region_overlay_paths, resolve_choices, seam_decision)
```

Then add the endpoint after `compose` (after `server/app.py:140`):

```python
@app.post("/api/overlay", response_model=models.OverlayResponse)
def overlay(req: models.OverlayRequest):
    sess = _get(req.imageId)
    if sess is None:
        raise HTTPException(status_code=404, detail={"error": "imageId desconocido"})
    if not (0 <= req.regionIndex < len(sess.regions)):
        raise HTTPException(status_code=400,
                            detail={"error": f"regionIndex fuera de rango: {req.regionIndex}"})
    r = sess.regions[req.regionIndex]
    chars = [c for c in r.text if not c.isspace()]
    if r.classification != "type" or not r.glyph_boxes or len(chars) != len(r.glyph_boxes):
        raise HTTPException(status_code=400,
                            detail={"error": "región sin texto tipográfico"})
    try:
        pairs, _ = region_overlay_paths(r, req.family, req.wght, CACHE_DIR_DEFAULT)
    except FontKeyError as e:
        raise HTTPException(status_code=422, detail={"error": str(e)})
    return models.OverlayResponse(
        glyphs=[models.GlyphPath(d=d, transform=tr) for d, tr in pairs])
```

- [ ] **Step 4: Run tests to verify they pass + full suite**

Run: `python -m pytest tests/test_server.py -k overlay -v`
Expected: PASS (gated e2e skips without the font cache).

Run: `python -m pytest -q`
Expected: the whole repo suite passes (B1's 134 + the new C0 tests; gated tests skip without the font cache).

- [ ] **Step 5: Commit**

```bash
git add server/app.py tests/test_server.py
git commit -m "feat(server): POST /api/overlay (geometria fiel de la candidata, reusa region_overlay_paths)" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- §2 contract (request/response shape) → Task 2 (DTOs) + Task 3 (endpoint).
- §2 errors 404/400/422 → Task 3 error tests (`404_imageid`, `400_region_fuera_de_rango`, `400_region_no_tipografica`, `400_charcount_no_cuadra`, `422_fontkey`, `422_body_invalido`).
- §3 core change (`region_overlay_paths`, one owner) → Task 1.
- §4 endpoint (sync, reuses `CACHE_DIR_DEFAULT`, no store write) → Task 3.
- §5 DTOs → Task 2.
- §6 acceptance: fidelity (overlay == compose type paths) → Task 1 gated test (core) + Task 3 gated e2e (server); no-regression (compose byte-identical) → Task 1 Step 4 full suite. **On the dev machine the font cache is present, so both gated tests RUN — they are the live acceptance here and must be green, not skipped. Capture the true baseline test count with `python -m pytest -q` before Task 1 rather than trusting the descriptive "134".**
- §7 out-of-scope (`/analyze` untouched, no precompute) → respected: no task touches `/analyze`.

**Type consistency:** `region_overlay_paths(region, family, wght, cache_dir) -> (pairs, ttf)` used identically in Task 1 (definition + compose loop) and Task 3 (`pairs, _ = region_overlay_paths(...)`). DTO names `OverlayRequest`/`GlyphPath`/`OverlayResponse` consistent across Tasks 2 and 3. `_raise_fontkey` reused from the existing test_server.py helper (line 169).

**Placeholder scan:** none — every step has full code and exact commands.
