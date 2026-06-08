"""server/models.py — DTOs Pydantic del wire (Spec B1 §5).

Derivados de las dataclasses RegionAnalysis/RankEntry de fontid; el test de
isomorfismo (tests/test_server.py) vigila que un campo nuevo de la dataclass se
decida explícitamente (mapeado o excluido), no que derive en silencio.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RankEntryDTO(BaseModel):
    family: str
    wght: int
    score: float
    tie: bool


class ChoiceDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")   # el wire no acepta campos extra (typos)
    family: str
    wght: int


class RegionDTO(BaseModel):
    index: int
    bbox: tuple[int, int, int, int]
    text: str
    classification: str
    classScore: float
    decision: Literal["tie", "leader", "no_font", "vectorized"]
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
    model_config = ConfigDict(extra="forbid")
    imageId: str
    choices: dict[str, ChoiceDTO] = Field(default_factory=dict)
    contourSigma: float = 2.0


class IndexText(BaseModel):
    index: int
    text: str


class ComposeResponse(BaseModel):
    svg: str
    provenance: list[str]
    ignoradas: list[IndexText] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    """Cuerpo de error tipado en el OpenAPI (spec §6). Viaja dentro del envelope
    `{"detail": ...}` de FastAPI; `pendientes` solo en el 400 de empate."""
    error: str
    pendientes: list[IndexText] | None = None


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
