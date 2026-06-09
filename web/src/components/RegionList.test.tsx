import { render, screen } from '@testing-library/react'
import { RegionList } from './RegionList'
import type { Region } from '../api/types'

const regions: Region[] = [
  { index: 0, bbox: [0,0,1,1], text: 'mente', classification: 'type', classScore: 0.9, decision: 'tie',
    candidates: [{ family: 'A', wght: 400, score: 0.8, tie: false }, { family: 'B', wght: 400, score: 0.79, tie: true }] },
  { index: 1, bbox: [0,0,1,1], text: 'TAG', classification: 'type', classScore: 0.9, decision: 'leader', chosen: { family: 'Lora', wght: 400 } },
  { index: 2, bbox: [0,0,1,1], text: '—', classification: 'handwriting', classScore: 0.2, decision: 'vectorized', reason: 'trazo' },
  { index: 3, bbox: [0,0,1,1], text: 'X', classification: 'type', classScore: 0.5, decision: 'no_font', reason: 'sin fuente' },
]

test('cada decisión tiene su badge en el riel', () => {
  render(<RegionList regions={regions} active={0} choices={{}} onPick={() => {}} />)
  expect(screen.getByText('empate')).toBeInTheDocument()       // tie
  expect(screen.getByText('líder')).toBeInTheDocument()        // leader
  expect(screen.getByText('vectorizado')).toBeInTheDocument()  // vectorized
  expect(screen.getByText('sin fuente')).toBeInTheDocument()   // no_font (meta = "sin candidatas", único)
})

test('una región elegida muestra el badge elegida', () => {
  render(<RegionList regions={regions} active={0} choices={{ 0: { family: 'A', wght: 400 } }} onPick={() => {}} />)
  expect(screen.getByText('elegida')).toBeInTheDocument()
})
