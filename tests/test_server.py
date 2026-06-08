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
    nuevo = srv._put(srv.Session(object(), [], 1, 1))
    assert srv._get(nuevo) is not None     # sigue funcionando tras clear
    srv._clear()
