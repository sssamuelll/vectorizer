import { expect, test } from 'vitest'
import { API_BASE } from './client'

// Verifica que los campos que C1a lee/escribe existen en el OpenAPI vivo.
// Skip si el backend no responde (no rompe la suite offline).
async function openapi(): Promise<any | null> {
  try {
    const res = await fetch(`${API_BASE}/openapi.json`)
    if (!res.ok) return null
    return await res.json()
  } catch { return null }
}

test('el contrato del backend cubre los campos que C1a usa', async () => {
  const spec = await openapi()
  if (!spec) { console.warn('backend no disponible; contrato omitido'); return }
  const props = (name: string) => Object.keys(spec.components?.schemas?.[name]?.properties ?? {})
  expect(props('RegionDTO')).toEqual(expect.arrayContaining(
    ['index', 'bbox', 'text', 'classification', 'classScore', 'decision', 'candidates', 'chosen', 'reason']))
  expect(props('AnalyzeResponse')).toEqual(expect.arrayContaining(
    ['imageId', 'width', 'height', 'colorWarning', 'regions']))
  expect(props('OverlayResponse')).toEqual(expect.arrayContaining(['glyphs']))
  expect(props('GlyphPath')).toEqual(expect.arrayContaining(['d', 'transform']))
  expect(props('OverlayRequest')).toEqual(expect.arrayContaining(['imageId', 'regionIndex', 'family', 'wght']))
  expect(props('ComposeResponse')).toEqual(expect.arrayContaining(['svg', 'provenance', 'ignoradas']))
})
