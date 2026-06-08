import { render, screen } from '@testing-library/react'
import { Rail } from './Rail'
import type { Region } from '../api/types'

const regions: Region[] = [
  { index: 0, bbox: [0,0,1,1], text: 'mente', classification: 'type', classScore: 0.9, decision: 'tie',
    candidates: [{ family: 'A', wght: 400, score: 0.8, tie: false }, { family: 'B', wght: 400, score: 0.79, tie: true }] },
  { index: 1, bbox: [0,0,1,1], text: 'TAG', classification: 'type', classScore: 0.9, decision: 'leader', chosen: { family: 'Lora', wght: 400 } },
  { index: 2, bbox: [0,0,1,1], text: '—', classification: 'handwriting', classScore: 0.2, decision: 'vectorized', reason: 'trazo' },
  { index: 3, bbox: [0,0,1,1], text: 'X', classification: 'type', classScore: 0.5, decision: 'no_font', reason: 'sin fuente' },
]

test('cada decisión tiene un badge, y el contador refleja ties elegidas', () => {
  const { container } = render(<Rail regions={regions} active={0} choices={{}} complete={false} doneCount={0} tieCount={1}
               onPick={() => {}} onDownload={() => {}} />)
  expect(screen.getByText('empate')).toBeInTheDocument()        // badge tie
  expect(screen.getByText('líder')).toBeInTheDocument()         // badge leader
  expect(screen.getByText('vectorizado')).toBeInTheDocument()   // badge vectorized
  expect(screen.getByText('sin fuente')).toBeInTheDocument()    // badge no_font (la meta dice "sin candidatas", único)
  // el contador está partido por <b>; se lee del nodo .counter, no por substring
  expect(container.querySelector('.counter')?.textContent).toBe('0 de 1 elegidas')
})

test('el botón de descarga está deshabilitado hasta complete', () => {
  const { rerender } = render(<Rail regions={regions} active={0} choices={{}} complete={false}
                                    doneCount={0} tieCount={1} onPick={() => {}} onDownload={() => {}} />)
  expect(screen.getByRole('button', { name: /descargar svg/i })).toBeDisabled()
  rerender(<Rail regions={regions} active={0} choices={{ 0: { family: 'A', wght: 400 } }} complete
                 doneCount={1} tieCount={1} onPick={() => {}} onDownload={() => {}} />)
  expect(screen.getByRole('button', { name: /descargar svg/i })).toBeEnabled()
})
