// Espejo de server/models.py. RegionDTO = unión discriminada sobre `decision`.

export type Choice = { family: string; wght: number }            // ChoiceDTO
export type RankEntry = { family: string; wght: number; score: number; tie: boolean }  // RankEntryDTO; score/tie NO se muestran (regla 5)
export type Bbox = [number, number, number, number]
type RegionBase = { index: number; bbox: Bbox; text: string; classification: string; classScore: number }
export type Region =
  | (RegionBase & { decision: 'tie'; candidates: RankEntry[] })
  | (RegionBase & { decision: 'leader'; chosen: Choice })
  | (RegionBase & { decision: 'no_font'; reason: string })
  | (RegionBase & { decision: 'vectorized'; reason: string })
export type AnalyzeResponse = {
  imageId: string; width: number; height: number; colorWarning: string | null; regions: Region[]
}
export type GlyphPath = { d: string; transform: string }          // GlyphPath
export type OverlayResponse = { glyphs: GlyphPath[] }              // OverlayResponse
export type OverlayRequest = { imageId: string; regionIndex: number; family: string; wght: number }
export type ComposeRequest = { imageId: string; choices: Record<string, Choice> }  // contourSigma omitido → default server
export type IndexText = { index: number; text: string }
export type ComposeResponse = { svg: string; provenance: string[]; ignoradas: IndexText[] }
