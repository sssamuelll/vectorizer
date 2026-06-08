"""Tests del server FastAPI (Spec B1)."""
import dataclasses
import sys
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fontid
import server.app as srv
import server.models as models


def _rank(*tuples):
    return [fontid.RankEntry(f, w, s, t) for f, w, s, t in tuples]


def _region(text, classification="type", score=0.9, ranking=None, n_glyphs=3):
    boxes = [(i * 10, 0, i * 10 + 8, 20) for i in range(n_glyphs)]
    return fontid.RegionAnalysis(bbox=(0, 0, 100, 20), text=text,
                                 classification=classification, class_score=score,
                                 glyph_boxes=boxes, ranking=ranking or [])


def _dummy_raster():
    return np.zeros((20, 100, 3), np.uint8)


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


def test_store_put_ids_distintos():
    """Dos _put → imageIds distintos (no singleton, contrato del uuid)."""
    a = srv._put(srv.Session(object(), [], 1, 1))
    b = srv._put(srv.Session(object(), [], 1, 1))
    assert a != b
    srv._clear()


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


def test_region_dto_preserva_valores_y_rename():
    """class_score (dataclass) → classScore (DTO) y aridad de bbox, vía round-trip
    JSON. Cierra el agujero del rename: el isomorfismo de NOMBRES no verifica que
    el valor aterrice en el campo renombrado (la crítica de Richter)."""
    r = fontid.RegionAnalysis(
        bbox=(1, 2, 3, 4), text="mente", classification="type",
        class_score=0.9, glyph_boxes=[], ranking=[])
    dto = models.RegionDTO(
        index=0, bbox=r.bbox, text=r.text, classification=r.classification,
        classScore=r.class_score, decision="no_font", reason="sin ranking")
    back = models.RegionDTO.model_validate_json(dto.model_dump_json())
    assert back.classScore == r.class_score      # el rename aterriza CON el valor
    assert back.bbox == (1, 2, 3, 4)             # tupla de aridad fija sobrevive JSON


def test_analyze_deriva_las_4_decisiones(monkeypatch):
    fake = [
        _region("mente", ranking=_rank(("Cormorant Garamond", 500, 0.753, False),
                                       ("Libre Baskerville", 400, 0.747, True))),   # tie
        _region("abc", ranking=_rank(("Lora", 400, 0.80, False))),                  # leader
        _region("libre", classification="handwriting", score=0.2),                  # vectorized
        _region("xy", ranking=[]),                                                  # no_font
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
    assert regs[1]["classScore"] == 0.9    # el rename class_score->classScore lleva el valor


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
