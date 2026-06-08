import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi, beforeEach, afterEach, test, expect } from 'vitest'
import App from './App'
import * as client from './api/client'
import type { AnalyzeResponse } from './api/types'

beforeEach(() => {
  globalThis.URL.createObjectURL = vi.fn(() => 'blob:1')
  globalThis.URL.revokeObjectURL = vi.fn()
})
afterEach(() => vi.restoreAllMocks())

const twoTies: AnalyzeResponse = {
  imageId: 'img1', width: 300, height: 120, colorWarning: null,
  regions: [
    { index: 0, bbox: [0,0,1,1], text: 'mente', classification: 'type', classScore: 0.9, decision: 'tie',
      candidates: [{ family: 'A', wght: 400, score: 0.8, tie: false }, { family: 'B', wght: 400, score: 0.79, tie: true }] },
    { index: 1, bbox: [0,0,1,1], text: 'TAG', classification: 'type', classScore: 0.9, decision: 'tie',
      candidates: [{ family: 'C', wght: 600, score: 0.8, tie: false }, { family: 'D', wght: 600, score: 0.79, tie: true }] },
  ],
}

test('happy path: subir → elegir 2 empates → descargar', async () => {
  vi.spyOn(client, 'analyze').mockResolvedValue(twoTies)
  vi.spyOn(client, 'overlay').mockResolvedValue({ glyphs: [{ d: 'M0Z', transform: 'matrix(1)' }] })
  vi.spyOn(client, 'compose').mockResolvedValue({ svg: '<svg xmlns="http://www.w3.org/2000/svg"/>', provenance: ['ok'], ignoradas: [] })

  const { container } = render(<App />)
  await userEvent.upload(container.querySelector('input[type=file]')!, new File(['d'], 'logo.png', { type: 'image/png' }))

  await screen.findByText(/cuál calza/i)                       // choose screen
  await userEvent.click(await screen.findByRole('button', { name: /^A/ }))   // elige región 0
  await userEvent.click(await screen.findByRole('button', { name: /^C/ }))   // elige región 1
  const dl = await screen.findByRole('button', { name: /descargar svg/i })
  await waitFor(() => expect(dl).toBeEnabled())
  await userEvent.click(dl)
  expect(await screen.findByText(/tu svg está armado/i)).toBeInTheDocument()
})

test('logo sin texto → EmptyState (no pantalla de elección vacía)', async () => {
  vi.spyOn(client, 'analyze').mockResolvedValue(
    { imageId: 'img2', width: 100, height: 100, colorWarning: '~13 colores', regions: [] })
  const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
  const { container } = render(<App />)
  await userEvent.upload(container.querySelector('input[type=file]')!, new File(['d'], 'graf.png', { type: 'image/png' }))
  expect(await screen.findByText(/no encontramos texto/i)).toBeInTheDocument()
  expect(warn).toHaveBeenCalledWith(expect.stringContaining('colores'))
})

test('fallo de analyze → pantalla de error con reintentar', async () => {
  vi.spyOn(client, 'analyze').mockRejectedValue(new client.ApiError(503, 'el análisis no respondió'))
  const { container } = render(<App />)
  await userEvent.upload(container.querySelector('input[type=file]')!, new File(['d'], 'x.png', { type: 'image/png' }))
  expect(await screen.findByText(/el análisis no respondió/i)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /reintentar|re-subir/i })).toBeInTheDocument()
})
