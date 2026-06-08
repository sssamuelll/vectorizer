"""Tests del server FastAPI (Spec B1)."""
import dataclasses
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fontid
import server.app as srv
import server.models as models


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
