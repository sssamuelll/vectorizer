import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { CandidateRail } from './CandidateRail'
import type { RankEntry } from '../api/types'

const cands: RankEntry[] = [
  { family: 'DM Serif Display', wght: 400, score: 0.81, tie: false },
  { family: 'Playfair Display', wght: 700, score: 0.80, tie: true },
]

test('renderiza una tarjeta por candidata con familia y peso, sin score', () => {
  render(<CandidateRail text="VERANO" candidates={cands} chosen={null} armed={null}
                        onArm={() => {}} onChoose={() => {}} />)
  expect(screen.getByText('DM Serif Display')).toBeInTheDocument()
  expect(screen.getByText('Playfair Display')).toBeInTheDocument()
  expect(screen.queryByText('0.81')).not.toBeInTheDocument()   // score oculto (regla 5)
})

test('hover arma; clic elige', async () => {
  const onArm = vi.fn(); const onChoose = vi.fn()
  render(<CandidateRail text="VERANO" candidates={cands} chosen={null} armed={null}
                        onArm={onArm} onChoose={onChoose} />)
  const card = screen.getByRole('button', { name: /DM Serif Display/ })
  await userEvent.hover(card)
  expect(onArm).toHaveBeenCalledWith({ family: 'DM Serif Display', wght: 400 })
  await userEvent.click(card)
  expect(onChoose).toHaveBeenCalledWith({ family: 'DM Serif Display', wght: 400 })
})

test('marca la candidata elegida', () => {
  render(<CandidateRail text="VERANO" candidates={cands} chosen={{ family: 'Playfair Display', wght: 700 }}
                        armed={null} onArm={() => {}} onChoose={() => {}} />)
  const chosen = screen.getByRole('button', { name: /Playfair Display/ })
  expect(chosen.className).toMatch(/chosen/)
})
