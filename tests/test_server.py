"""Tests del server FastAPI (Spec B1)."""
import dataclasses
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fontid
import server.app as srv
import server.models as models

CACHE = Path.home() / ".cache" / "vectorizer-fonts"
TTF_TEST = CACHE / "Cormorant_Garamond_500.ttf"


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


def test_analyze_sin_regiones_200_vacio(monkeypatch):
    """Sin regiones detectadas → 200 con regions vacío (no es error)."""
    monkeypatch.setattr(srv, "load_image_bgr_from_bytes", lambda d: _dummy_raster())
    monkeypatch.setattr(srv, "count_effective_colors", lambda r: 3)
    monkeypatch.setattr(srv, "analyze_regions", lambda r: [])
    client = TestClient(srv.app)
    resp = client.post("/api/analyze", files={"file": ("x.png", b"d", "image/png")})
    assert resp.status_code == 200 and resp.json()["regions"] == []


def test_analyze_colorwarning_presente(monkeypatch):
    """count_effective_colors > umbral → colorWarning no-null (la única rama del aviso)."""
    monkeypatch.setattr(srv, "load_image_bgr_from_bytes", lambda d: _dummy_raster())
    monkeypatch.setattr(srv, "count_effective_colors", lambda r: 20)
    monkeypatch.setattr(srv, "analyze_regions", lambda r: [])
    client = TestClient(srv.app)
    resp = client.post("/api/analyze", files={"file": ("x.png", b"d", "image/png")})
    assert resp.status_code == 200
    cw = resp.json()["colorWarning"]
    assert cw is not None and "20" in cw


def test_analyze_runtimeerror_503(monkeypatch):
    """analyze_regions lanza RuntimeError (OCR sin idioma / metadata GF caída cold-cache)
    → 503 con envelope, no un 500 crudo (el CLI lo atrapa, el server también)."""
    monkeypatch.setattr(srv, "load_image_bgr_from_bytes", lambda d: _dummy_raster())
    monkeypatch.setattr(srv, "count_effective_colors", lambda r: 3)

    def _boom(r):
        raise RuntimeError("metadata GF no disponible")

    monkeypatch.setattr(srv, "analyze_regions", _boom)
    client = TestClient(srv.app)
    resp = client.post("/api/analyze", files={"file": ("x.png", b"d", "image/png")})
    assert resp.status_code == 503 and "metadata" in resp.json()["detail"]["error"]


def _raise_fontkey(*a, **k):
    raise srv.FontKeyError("peso 999 no disponible para 'Lora'; disponibles: [400]")


def test_compose_404_imageid_desconocido():
    client = TestClient(srv.app)
    resp = client.post("/api/compose", json={"imageId": "noexiste", "choices": {}})
    assert resp.status_code == 404 and resp.json()["detail"]["error"] == "imageId desconocido"


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
    assert resp.status_code == 422 and "999" in resp.json()["detail"]["error"]


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


def test_compose_ignoradas_en_respuesta(monkeypatch):
    """choice sobre región no-recompuesta (handwriting) → aparece en ignoradas (espeja el [WARN]
    del CLI, no se traga). Hay otra región recomponible para no caer en 422."""
    from recompose_core import ComposeResult
    regions = [_region("abc", ranking=_rank(("Lora", 400, 0.8, False))),     # leader → recompone
               _region("libre", classification="handwriting", score=0.2)]    # no recompone
    sid = srv._put(srv.Session(_dummy_raster(), regions, 100, 20))
    monkeypatch.setattr(srv, "compose_hybrid_svg",
                        lambda *a, **k: ComposeResult("<svg/>", "#000", 1, 3, [], [(0, 0, 100, 20)]))
    client = TestClient(srv.app)
    resp = client.post("/api/compose", json={"imageId": sid,
                                             "choices": {"1": {"family": "Lora", "wght": 400}}})
    assert resp.status_code == 200
    assert resp.json()["ignoradas"] == [{"index": 1, "text": "libre"}]


def test_compose_clave_unicode_digito_400():
    """Clave dígito-unicode ('²'): isdigit() True pero int() lanzaría — debe ser 400, no 500."""
    regions = [_region("abc", ranking=_rank(("Lora", 400, 0.8, False)))]
    sid = srv._put(srv.Session(_dummy_raster(), regions, 100, 20))
    client = TestClient(srv.app)
    resp = client.post("/api/compose",
                       json={"imageId": sid, "choices": {"²": {"family": "Lora", "wght": 400}}})
    assert resp.status_code == 400


def test_compose_empate_con_eleccion_fluye_y_reenvia_sigma(monkeypatch):
    """Región empate CON elección → 200: la elección resuelve el empate y llega a
    compose_hybrid_svg, y contourSigma se reenvía (no se hardcodea)."""
    from recompose_core import ComposeResult
    regions = [_region("mente", ranking=_rank(("A", 500, 0.75, False), ("B", 400, 0.745, True)))]
    sid = srv._put(srv.Session(_dummy_raster(), regions, 100, 20))
    cap = {}

    def fake_compose(img, regs, choices, recomp_idx, sigma, cache_dir):
        cap["choices"] = dict(choices)
        cap["sigma"] = sigma
        return ComposeResult("<svg/>", "#000", 1, 3, [], [(0, 0, 100, 20)])

    monkeypatch.setattr(srv, "compose_hybrid_svg", fake_compose)
    client = TestClient(srv.app)
    resp = client.post("/api/compose", json={
        "imageId": sid, "choices": {"0": {"family": "Nanum Myeongjo", "wght": 400}},
        "contourSigma": 3.5})
    assert resp.status_code == 200
    assert cap["choices"][0] == ("Nanum Myeongjo", 400)   # la elección llegó a compose
    assert cap["sigma"] == 3.5                            # contourSigma se reenvía


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
