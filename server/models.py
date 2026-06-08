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
