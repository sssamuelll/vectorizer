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
