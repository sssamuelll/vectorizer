import { render, screen, fireEvent } from '@testing-library/react'
import { ChooseScreen } from './ChooseScreen'
import { initialState, cacheKey, type AppState } from '../state/useApp'
import type { AnalyzeResponse, GlyphPath } from '../api/types'

const analysis: AnalyzeResponse = {
  imageId: 'img1', width: 300, height: 120, colorWarning: null,
  regions: [
    { index: 0, bbox: [0,0,1,1], text: 'A', classification: 'type', classScore: 0.9, decision: 'tie',
      candidates: [{ family: 'FA', wght: 400, score: 0.8, tie: false }, { family: 'FB', wght: 400, score: 0.79, tie: true }] },
    { index: 1, bbox: [0,0,1,1], text: 'B', classification: 'type', classScore: 0.9, decision: 'tie',
      candidates: [{ family: 'FC', wght: 600, score: 0.8, tie: false }, { family: 'FD', wght: 600, score: 0.79, tie: true }] },
  ],
}
function choosing(): AppState {
  const cache = new Map<string, GlyphPath[]>()
  cache.set(cacheKey('img1', 0, { family: 'FA', wght: 400 }), [{ d: 'M0Z', transform: 't0' }])
  cache.set(cacheKey('img1', 1, { family: 'FC', wght: 600 }), [{ d: 'M1Z', transform: 't1' }])  // región NO activa
  return { ...initialState, phase: 'choosing', objectURL: 'blob:1', analysis,
           activeRegion: 0, armed: { family: 'FA', wght: 400 }, overlayCache: cache }
}

test('active-only: pinta solo el glifo de la región activa, no el de la otra', () => {
  const { container } = render(<ChooseScreen state={choosing()} onArm={() => {}} onChoose={() => {}} />)
  const paths = container.querySelectorAll('svg.overlay-layer path')
  expect(paths).toHaveLength(1)
  expect(paths[0].getAttribute('d')).toBe('M0Z')          // región 0; la 1 (M1Z) NO se pinta
})

test('mantener para ver original oculta la capa de overlay', () => {
  const { container } = render(<ChooseScreen state={choosing()} onArm={() => {}} onChoose={() => {}} />)
  const svg = () => container.querySelector('svg.overlay-layer') as SVGElement
  expect(svg().style.visibility).toBe('visible')
  fireEvent.mouseDown(screen.getByText(/mantener para ver original/i))
  expect(svg().style.visibility).toBe('hidden')
  fireEvent.mouseUp(screen.getByText(/mantener para ver original/i))
  expect(svg().style.visibility).toBe('visible')
})
