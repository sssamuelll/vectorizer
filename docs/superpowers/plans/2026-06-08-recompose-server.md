# Spec B1 — Server FastAPI — Plan de Implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un server FastAPI loopback con `/api/analyze` + `/api/compose` que envuelve el core
(B0/A) y produce, por `TestClient`, un SVG byte-idéntico al CLI sobre el logo de Ale.

**Architecture:** Dos endpoints **sync** (FastAPI los corre en el threadpool). El estado vive en
un store inline `dict[imageId, Session]` con lock (Session = raster + RegionAnalysis reales);
`/compose` compone con los objetos server-side, no reconstruye del wire. La política
`empate>líder>error` la posee el `resolve_choices` compartido de B0 — un solo dueño con el CLI.
DTOs Pydantic derivados de las dataclasses, con un test de isomorfismo que falla si una dataclass
gana un campo no decidido.

**Tech Stack:** FastAPI, uvicorn, python-multipart, httpx (TestClient) — ya instalados. Core: B0/A.

**Spec:** `docs/superpowers/specs/2026-06-08-recompose-server-design.md`

---

## Estructura de archivos

| archivo | responsabilidad | acción |
|---|---|---|
| `server/__init__.py` | paquete | crear (vacío) |
| `server/app.py` | FastAPI: lifespan, store inline, los 2 endpoints, `_decision` | crear |
| `server/models.py` | DTOs Pydantic del wire | crear |
| `server/__main__.py` | `python -m server` → uvicorn 127.0.0.1 | crear |
| `tests/test_server.py` | tests del server (TestClient, sintéticos) | crear |
| `requirements.txt` | declarar las 4 deps del server | modificar |

---

## Task 1: Scaffold del paquete — store + app skeleton + deps

**Files:** Create `server/__init__.py`, `server/app.py`, `server/__main__.py`; Modify `requirements.txt`;
Test `tests/test_server.py`.

- [ ] **Step 1: Declarar las deps en `requirements.txt`**

Añadir al final de `requirements.txt`:
```
# server (Spec B1 — backend FastAPI loopback):
fastapi>=0.115
uvicorn[standard]>=0.30
python-multipart>=0.0.9   # uploads multipart de /api/analyze
# dev: httpx para fastapi.testclient
httpx>=0.27
```

- [ ] **Step 2: Crear el paquete + el store + el app skeleton**

`server/__init__.py`: vacío (paquete).

`server/app.py`:
```python
"""server/app.py — backend FastAPI (Spec B1). Loopback, 2 endpoints, store inline.

Envuelve el core (A/B0): analyze_regions, resolve_choices, compose_hybrid_svg,
load_image_bgr_from_bytes. NO duplica nada. Endpoints sync (threadpool de anyio).
"""
import threading
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


# ── store inline (spec §2) ──────────────────────────────────────────
@dataclass
class Session:
    raster: object        # np.ndarray BGR del upload
    regions: list         # [RegionAnalysis]
    width: int
    height: int


_SESSIONS: dict = {}
_LOCK = threading.Lock()


def _put(sess):
    """Guarda una sesión bajo un imageId uuid (no singleton, no adivinable)."""
    sid = uuid.uuid4().hex
    with _LOCK:
        _SESSIONS[sid] = sess
    return sid


def _get(sid):
    """Sesión por imageId, o None si no existe (expiró / reinicio)."""
    with _LOCK:
        return _SESSIONS.get(sid)


def _clear():
    with _LOCK:
        _SESSIONS.clear()


@asynccontextmanager
async def lifespan(app):
    yield
    _clear()          # material de cliente no persiste un reinicio (spec §2)


app = FastAPI(title="recompose", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["http://localhost:5173"],   # Vite dev (para C)
    allow_methods=["*"], allow_headers=["*"])
```

`server/__main__.py`:
```python
"""python -m server → uvicorn en loopback (Spec B1)."""
import uvicorn

uvicorn.run("server.app:app", host="127.0.0.1", port=8000)
```

- [ ] **Step 3: Escribir el test del store (falla: no existe el módulo)**

`tests/test_server.py`:
```python
"""Tests del server FastAPI (Spec B1)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server.app as srv


def test_store_put_get_roundtrip():
    sess = srv.Session(raster=object(), regions=[], width=10, height=20)
    sid = srv._put(sess)
    assert isinstance(sid, str) and len(sid) >= 8
    assert srv._get(sid) is sess


def test_store_get_desconocido_es_none():
    assert srv._get("noexiste") is None


def test_store_clear_vacia():
    srv._put(srv.Session(object(), [], 1, 1))
    srv._clear()
    assert srv._get(srv._put(srv.Session(object(), [], 1, 1)))  # sigue funcionando tras clear
    srv._clear()
```

- [ ] **Step 4: Correr — pasan**

Run: `python -m pytest tests/test_server.py -q`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add server/ tests/test_server.py requirements.txt
git commit -m "feat(server): scaffold FastAPI + store inline (dict+lock+uuid, lifespan limpia)"
```

---

## Task 2: `server/models.py` — DTOs Pydantic + test de isomorfismo

**Files:** Create `server/models.py`; Test `tests/test_server.py`.

- [ ] **Step 1: Escribir el test de isomorfismo (falla: no existe models)**

Añadir a `tests/test_server.py`:
```python
import dataclasses
import fontid
import server.models as models


def test_rankentry_dto_isomorfismo():
    """RankEntry mapea 1:1 a RankEntryDTO — si la dataclass gana un campo, falla."""
    dc = {f.name for f in dataclasses.fields(fontid.RankEntry)}
    dto = set(models.RankEntryDTO.model_fields)
    assert dc == dto, f"RankEntry vs DTO divergen: {dc ^ dto}"


def test_region_dto_isomorfismo():
    """Cada campo de RegionAnalysis está MAPEADO al DTO o EXCLUIDO-con-razón.
    Un campo nuevo no clasificado rompe el test (cierra el salto dataclass→wire)."""
    dc = {f.name for f in dataclasses.fields(fontid.RegionAnalysis)}
    MAPEADO = {"bbox", "text", "classification", "class_score"}   # → bbox/text/classification/classScore
    EXCLUIDO = {
        "glyph_boxes",   # interno: el server compone server-side, no va al wire
        "ranking",       # derivado a decision/candidates/chosen (no se manda crudo)
    }
    sin_clasificar = dc - (MAPEADO | EXCLUIDO)
    assert not sin_clasificar, f"campos de RegionAnalysis sin decidir para el wire: {sin_clasificar}"
```

- [ ] **Step 2: Correr — falla**

Run: `python -m pytest tests/test_server.py -k isomorfismo -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'server.models'`.

- [ ] **Step 3: Implementar `server/models.py`**

```python
"""server/models.py — DTOs Pydantic del wire (Spec B1 §5).

Derivados de las dataclasses RegionAnalysis/RankEntry de fontid; el test de
isomorfismo (tests/test_server.py) vigila que un campo nuevo de la dataclass se
decida explícitamente (mapeado o excluido), no que derive en silencio.
"""
from pydantic import BaseModel


class RankEntryDTO(BaseModel):
    family: str
    wght: int
    score: float
    tie: bool


class ChoiceDTO(BaseModel):
    family: str
    wght: int


class RegionDTO(BaseModel):
    index: int
    bbox: tuple[int, int, int, int]
    text: str
    classification: str
    classScore: float
    decision: str                              # tie | leader | no_font | vectorized
    candidates: list[RankEntryDTO] | None = None   # solo decision=="tie"
    chosen: ChoiceDTO | None = None                # solo decision=="leader"
    reason: str | None = None                      # no_font / vectorized


class AnalyzeResponse(BaseModel):
    imageId: str
    width: int
    height: int
    colorWarning: str | None = None
    regions: list[RegionDTO]


class ComposeRequest(BaseModel):
    imageId: str
    choices: dict[str, ChoiceDTO] = {}
    contourSigma: float = 2.0


class IndexText(BaseModel):
    index: int
    text: str


class ComposeResponse(BaseModel):
    svg: str
    provenance: list[str]
    ignoradas: list[IndexText] = []
```

- [ ] **Step 4: Correr — pasan**

Run: `python -m pytest tests/test_server.py -k isomorfismo -q`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add server/models.py tests/test_server.py
git commit -m "feat(server): DTOs Pydantic + test de isomorfismo dataclass<->DTO"
```

---

## Task 3: `POST /api/analyze` + la derivación `_decision`

**Files:** Modify `server/app.py`; Test `tests/test_server.py`.

- [ ] **Step 1: Escribir los tests (fallan: no existe el endpoint)**

Añadir a `tests/test_server.py` (arriba, junto a los imports, añadir los helpers):
```python
import numpy as np
from fastapi.testclient import TestClient


def _rank(*tuples):
    return [fontid.RankEntry(f, w, s, t) for f, w, s, t in tuples]


def _region(text, classification="type", score=0.9, ranking=None, n_glyphs=3):
    boxes = [(i * 10, 0, i * 10 + 8, 20) for i in range(n_glyphs)]
    return fontid.RegionAnalysis(bbox=(0, 0, 100, 20), text=text,
                                 classification=classification, class_score=score,
                                 glyph_boxes=boxes, ranking=ranking or [])


def _dummy_raster():
    return np.zeros((20, 100, 3), np.uint8)


def test_analyze_deriva_las_4_decisiones(monkeypatch):
    fake = [
        _region("mente", ranking=_rank(("Cormorant Garamond", 500, 0.753, False),
                                       ("Libre Baskerville", 400, 0.747, True))),   # tie
        _region("abc", ranking=_rank(("Lora", 400, 0.80, False))),                  # leader
        _region("libre", classification="handwriting", score=0.2),                  # vectorized
        _region("xy", ranking=[]),                                                  # no_font (type sin ranking)
    ]
    monkeypatch.setattr(srv, "load_image_bgr_from_bytes", lambda d: _dummy_raster())
    monkeypatch.setattr(srv, "count_effective_colors", lambda r: 3)
    monkeypatch.setattr(srv, "analyze_regions", lambda r: fake)
    client = TestClient(srv.app)
    resp = client.post("/api/analyze", files={"file": ("x.png", b"data", "image/png")})
    assert resp.status_code == 200
    body = resp.json()
    assert body["colorWarning"] is None and len(body["imageId"]) >= 8
    regs = body["regions"]
    assert regs[0]["decision"] == "tie" and len(regs[0]["candidates"]) == 2
    assert regs[1]["decision"] == "leader" and regs[1]["chosen"] == {"family": "Lora", "wght": 400}
    assert regs[2]["decision"] == "vectorized" and regs[2]["candidates"] is None
    assert regs[3]["decision"] == "no_font"


def test_analyze_ilegible_415(monkeypatch):
    monkeypatch.setattr(srv, "load_image_bgr_from_bytes", lambda d: None)
    client = TestClient(srv.app)
    resp = client.post("/api/analyze", files={"file": ("x", b"basura", "application/octet-stream")})
    assert resp.status_code == 415


def test_decision_band_cap_4():
    """La banda de empate se corta a 4 (líder + empatadas), no más."""
    r = _region("mente", ranking=_rank(
        ("A", 500, 0.80, False), ("B", 400, 0.79, True), ("C", 400, 0.785, True),
        ("D", 400, 0.78, True), ("E", 400, 0.775, True)))
    kind, band, chosen, reason = srv._decision(r)
    assert kind == "tie" and len(band) == 4
```

- [ ] **Step 2: Correr — fallan**

Run: `python -m pytest tests/test_server.py -k "analyze or band" -q`
Expected: FAIL (404 del endpoint inexistente / `AttributeError` de `_decision`).

- [ ] **Step 3: Implementar `_decision` + `/api/analyze` en `server/app.py`**

Añadir los imports al tope de `server/app.py` (tras los existentes):
```python
from fastapi import File, HTTPException, UploadFile

from fontid import analyze_regions, CACHE_DIR_DEFAULT
from recompose_core import (COLOR_WARN_THRESHOLD, FontKeyError,
                            compose_hybrid_svg, resolve_choices, seam_decision)
from vectorize import count_effective_colors, load_image_bgr_from_bytes

from server import models
```

Y al final del archivo:
```python
def _decision(r):
    """Deriva la vista de la región desde seam_decision + ranking (no es estado
    nuevo). Devuelve (kind, band, chosen, reason)."""
    d = seam_decision(r, has_font=False)
    if not d.recompose:
        kind = "vectorized" if r.classification != "type" else "no_font"
        return kind, None, None, d.reason
    empate = len(r.ranking) > 1 and r.ranking[1].tie
    if empate:
        band = ([r.ranking[0]] + [e for e in r.ranking[1:] if e.tie])[:4]
        return "tie", band, None, None
    return "leader", None, r.ranking[0], None


@app.post("/api/analyze", response_model=models.AnalyzeResponse)
def analyze(file: UploadFile = File(...)):
    raster = load_image_bgr_from_bytes(file.file.read())
    if raster is None:
        raise HTTPException(status_code=415, detail="imagen vacía o ilegible")
    n = count_effective_colors(raster)
    color_warning = (f"~{n} colores efectivos — recompose asume UNA tinta"
                     if n > COLOR_WARN_THRESHOLD else None)
    regions = analyze_regions(raster)
    h, w = raster.shape[:2]
    sid = _put(Session(raster, regions, w, h))
    out = []
    for i, r in enumerate(regions):
        kind, band, chosen, reason = _decision(r)
        out.append(models.RegionDTO(
            index=i, bbox=tuple(int(v) for v in r.bbox), text=r.text,
            classification=r.classification, classScore=float(r.class_score),
            decision=kind, reason=reason,
            candidates=([models.RankEntryDTO(family=e.family, wght=e.wght,
                                             score=e.score, tie=e.tie) for e in band]
                        if band else None),
            chosen=(models.ChoiceDTO(family=chosen.family, wght=chosen.wght)
                    if chosen else None)))
    return models.AnalyzeResponse(imageId=sid, width=w, height=h,
                                  colorWarning=color_warning, regions=out)
```

- [ ] **Step 4: Correr — pasan + suite**

Run: `python -m pytest tests/test_server.py -q` → todos verdes.
Run: `python -m pytest tests/ -q` → 112 + los nuevos, sin regresión.

- [ ] **Step 5: Commit**

```bash
git add server/app.py tests/test_server.py
git commit -m "feat(server): POST /api/analyze (decision derivado, candidatas sin glifos, 415)"
```

---

## Task 4: `POST /api/compose`

**Files:** Modify `server/app.py`; Test `tests/test_server.py`.

- [ ] **Step 1: Escribir los tests (fallan: no existe el endpoint)**

Añadir a `tests/test_server.py`:
```python
def _raise_fontkey(*a, **k):
    raise srv.FontKeyError("peso 999 no disponible para 'Lora'; disponibles: [400]")


def test_compose_404_imageid_desconocido():
    client = TestClient(srv.app)
    resp = client.post("/api/compose", json={"imageId": "noexiste", "choices": {}})
    assert resp.status_code == 404


def test_compose_empate_sin_eleccion_400():
    regions = [_region("mente", ranking=_rank(("A", 500, 0.75, False), ("B", 400, 0.745, True)))]
    sid = srv._put(srv.Session(_dummy_raster(), regions, 100, 20))
    client = TestClient(srv.app)
    resp = client.post("/api/compose", json={"imageId": sid, "choices": {}})
    assert resp.status_code == 400
    assert resp.json()["detail"]["pendientes"][0]["index"] == 0


def test_compose_nada_que_recomponer_422():
    regions = [_region("libre", classification="handwriting", score=0.2)]
    sid = srv._put(srv.Session(_dummy_raster(), regions, 100, 20))
    client = TestClient(srv.app)
    resp = client.post("/api/compose", json={"imageId": sid, "choices": {}})
    assert resp.status_code == 422


def test_compose_clave_fuera_de_rango_400():
    regions = [_region("abc", ranking=_rank(("Lora", 400, 0.8, False)))]
    sid = srv._put(srv.Session(_dummy_raster(), regions, 100, 20))
    client = TestClient(srv.app)
    resp = client.post("/api/compose", json={"imageId": sid,
                                             "choices": {"7": {"family": "Lora", "wght": 400}}})
    assert resp.status_code == 400


def test_compose_fontkey_422(monkeypatch):
    regions = [_region("abc", ranking=_rank(("Lora", 400, 0.8, False)))]
    sid = srv._put(srv.Session(_dummy_raster(), regions, 100, 20))
    monkeypatch.setattr(srv, "compose_hybrid_svg", _raise_fontkey)
    client = TestClient(srv.app)
    resp = client.post("/api/compose", json={"imageId": sid,
                                             "choices": {"0": {"family": "Lora", "wght": 999}}})
    assert resp.status_code == 422 and "999" in resp.json()["detail"]


def test_compose_happy(monkeypatch):
    from recompose_core import ComposeResult
    regions = [_region("abc", ranking=_rank(("Lora", 400, 0.8, False)))]
    sid = srv._put(srv.Session(_dummy_raster(), regions, 100, 20))
    monkeypatch.setattr(srv, "compose_hybrid_svg",
                        lambda *a, **k: ComposeResult("<svg/>", "#000", 1, 3,
                                                      ["Lora:400 sha256:abcd"], [(0, 0, 100, 20)]))
    client = TestClient(srv.app)
    resp = client.post("/api/compose", json={"imageId": sid, "choices": {}})  # líder auto
    assert resp.status_code == 200
    body = resp.json()
    assert body["svg"] == "<svg/>" and body["provenance"] == ["Lora:400 sha256:abcd"]
    assert body["ignoradas"] == []
```

- [ ] **Step 2: Correr — fallan**

Run: `python -m pytest tests/test_server.py -k compose -q`
Expected: FAIL (404 del endpoint inexistente, etc.).

- [ ] **Step 3: Implementar `/api/compose` en `server/app.py`**

Añadir al final de `server/app.py`:
```python
@app.post("/api/compose", response_model=models.ComposeResponse)
def compose(req: models.ComposeRequest):
    sess = _get(req.imageId)
    if sess is None:
        raise HTTPException(status_code=404, detail="imageId desconocido")
    explicit = {}
    for k, v in req.choices.items():
        if not k.isdigit() or not (0 <= int(k) < len(sess.regions)):
            raise HTTPException(status_code=400, detail=f"índice de choices inválido: {k!r}")
        explicit[int(k)] = (v.family, v.wght)
    resolved = resolve_choices(sess.regions, explicit)
    if not resolved.recomp_idx:
        raise HTTPException(status_code=422, detail="nada que recomponer")
    if resolved.pendientes:
        raise HTTPException(status_code=400, detail={
            "error": "empate sin elección",
            "pendientes": [{"index": i, "text": r.text} for i, r in resolved.pendientes]})
    try:
        res = compose_hybrid_svg(sess.raster, sess.regions, resolved.effective,
                                 resolved.recomp_idx, req.contourSigma, CACHE_DIR_DEFAULT)
    except FontKeyError as e:
        raise HTTPException(status_code=422, detail=str(e))
    ignoradas = [models.IndexText(index=i, text=sess.regions[i].text)
                 for i in resolved.ignoradas]
    return models.ComposeResponse(svg=res.svg_text, provenance=res.provenance,
                                  ignoradas=ignoradas)
```

- [ ] **Step 4: Correr — pasan + suite**

Run: `python -m pytest tests/test_server.py -q` → todos verdes.
Run: `python -m pytest tests/ -q` → sin regresión. `python -m pyflakes server/app.py server/models.py` → limpio.

- [ ] **Step 5: Commit**

```bash
git add server/app.py tests/test_server.py
git commit -m "feat(server): POST /api/compose (resolve_choices compartido, 404/400/422)"
```

---

## Task 5: Gate de aceptación — `/compose` por TestClient byte-idéntico al CLI

**Files:** ninguno (verificación manual; el logo de Ale es material de cliente fuera del repo).

Gate de merge de B1: el server reproduce el CLI sobre el logo real.

- [ ] **Step 1: Correr el flujo /analyze→/compose por TestClient contra el logo de Ale**

Escribir un scratch `C:\Users\simon\AppData\Local\Temp\b1_accept.py` (NO commitear):
```python
import sys; sys.path.insert(0, r"C:\Users\simon\Desktop\projects\vectorizer")
from fastapi.testclient import TestClient
import server.app as srv

client = TestClient(srv.app)
ale = r"C:\Users\simon\Desktop\Ale\logo_ale.jpeg"
with open(ale, "rb") as f:
    a = client.post("/api/analyze", files={"file": ("logo.jpeg", f.read(), "image/jpeg")})
assert a.status_code == 200, a.text
body = a.json()
choices = {}
for reg in body["regions"]:
    t = reg["text"].strip().lower()
    if t == "mente":
        choices[str(reg["index"])] = {"family": "Nanum Myeongjo", "wght": 400}
    elif "integrative" in t:
        choices[str(reg["index"])] = {"family": "STIX Two Text", "wght": 600}
c = client.post("/api/compose", json={"imageId": body["imageId"],
                                      "choices": choices, "contourSigma": 2.0})
assert c.status_code == 200, c.text
svg = c.json()["svg"]
ref = open(r"C:\Users\simon\Desktop\Ale\logo_ale_v01.svg", encoding="utf-8").read()
print("BYTE-IDENTICO" if svg == ref else f"DIVERGE (server {len(svg)} vs ref {len(ref)})")
```
Run: `python "$env:TEMP\b1_accept.py"` (desde el repo root).
Expected: `BYTE-IDENTICO`.

> Si el OCR del logo no produce exactamente `mente` / `INTEGRATIVE PSYCHOLOGY` (variación de
> reconocimiento), ajustar el matcher de texto del scratch; el SVG sigue debiendo ser byte-idéntico
> una vez las dos regiones reciben sus fuentes. Cualquier diferencia de bytes es un fallo de B1.

- [ ] **Step 2: Suite + pyflakes finales**

Run: `python -m pytest tests/ -q` → todos verdes (112 + los del server).
Run: `python -m pyflakes server/app.py server/models.py server/__main__.py` → limpio.
Borrar el scratch: `Remove-Item "$env:TEMP\b1_accept.py"`. Si todo verde, B1 listo para PR.

---

## Self-Review (hecho al escribir el plan)

- **Cobertura del spec:** §1 módulos → Task 1/2. §2 store → Task 1. §3 `/analyze`+`_decision` →
  Task 3. §4 `/compose` → Task 4. §5 DTOs+isomorfismo → Task 2. §6 errores (404/400/422/415) →
  Task 3 (415) + Task 4 (404/400/422). §7 aceptación byte-idéntica → Task 5. §8 no-goals → respetados
  (sin token/lock/TTL/glifos/413). Deps → Task 1.
- **Placeholders:** ninguno. Endpoints, store, DTOs, `_decision` y los tests con código completo.
- **Consistencia de tipos:** `Session(raster, regions, width, height)`; `_put→str`, `_get→Session|None`;
  `_decision(r)→(kind, band, chosen, reason)`; `RegionDTO`/`RankEntryDTO`/`ChoiceDTO`/`AnalyzeResponse`/
  `ComposeRequest`/`ComposeResponse`/`IndexText` consistentes entre models.py (Task 2) y los endpoints
  (Task 3/4). `compose_hybrid_svg(...).svg_text/.provenance` y `resolve_choices(...).effective/.recomp_idx/
  .pendientes/.ignoradas` coinciden con las firmas de B0/A.
- **Nota de error envelope:** se usa la convención FastAPI `{"detail": ...}` (string, o dict con
  `pendientes` en el 400) en vez de un modelo `{error,...}` separado — idiomático y tipado por status
  en el OpenAPI; el spec §6 se satisface en intención (info estructurada + códigos).
