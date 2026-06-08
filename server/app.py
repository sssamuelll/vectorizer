"""server/app.py — backend FastAPI (Spec B1). Loopback, 2 endpoints, store inline.

Envuelve el core (A/B0): analyze_regions, resolve_choices, compose_hybrid_svg,
load_image_bgr_from_bytes. NO duplica nada. Endpoints sync (threadpool de anyio).
"""
import threading
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from fontid import analyze_regions, CACHE_DIR_DEFAULT
from recompose_core import (COLOR_WARN_THRESHOLD, FontKeyError, compose_hybrid_svg,
                            resolve_choices, seam_decision)
from vectorize import count_effective_colors, load_image_bgr_from_bytes

from server import models


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
        raise HTTPException(status_code=415, detail={"error": "imagen vacía o ilegible"})
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


@app.post("/api/compose", response_model=models.ComposeResponse)
def compose(req: models.ComposeRequest):
    sess = _get(req.imageId)
    if sess is None:
        raise HTTPException(status_code=404, detail={"error": "imageId desconocido"})
    explicit = {}
    for k, v in req.choices.items():
        if not k.isdigit() or not (0 <= int(k) < len(sess.regions)):
            raise HTTPException(status_code=400,
                                detail={"error": f"índice de choices inválido: {k!r}"})
        explicit[int(k)] = (v.family, v.wght)
    resolved = resolve_choices(sess.regions, explicit)
    if not resolved.recomp_idx:
        raise HTTPException(status_code=422, detail={"error": "nada que recomponer"})
    if resolved.pendientes:
        raise HTTPException(status_code=400, detail={
            "error": "empate sin elección",
            "pendientes": [{"index": i, "text": r.text} for i, r in resolved.pendientes]})
    try:
        res = compose_hybrid_svg(sess.raster, sess.regions, resolved.effective,
                                 resolved.recomp_idx, req.contourSigma, CACHE_DIR_DEFAULT)
    except FontKeyError as e:
        raise HTTPException(status_code=422, detail={"error": str(e)})
    ignoradas = [models.IndexText(index=i, text=sess.regions[i].text)
                 for i in resolved.ignoradas]
    return models.ComposeResponse(svg=res.svg_text, provenance=res.provenance,
                                  ignoradas=ignoradas)
