import { render, screen } from '@testing-library/react'
import { ComposeScreen } from './ComposeScreen'
import type { ComposeResponse } from '../api/types'

beforeAll(() => {
  // jsdom no implementa createObjectURL
  globalThis.URL.createObjectURL = vi.fn(() => 'blob:svg')
  globalThis.URL.revokeObjectURL = vi.fn()
})

const result: ComposeResponse = { svg: '<svg xmlns="http://www.w3.org/2000/svg"/>',
  provenance: ['DM Serif Display:400 sha256:abcd'], ignoradas: [] }

test('renderiza el SVG aislado (img blob) y un enlace de descarga', () => {
  render(<ComposeScreen result={result} onBack={() => {}} />)
  const img = screen.getByAltText(/svg recompuesto/i) as HTMLImageElement
  expect(img.getAttribute('src')).toBe('blob:svg')
  const link = screen.getByRole('link', { name: /descargar svg/i }) as HTMLAnchorElement
  expect(link.getAttribute('href')).toBe('blob:svg')
  expect(link.getAttribute('download')).toMatch(/\.svg$/)
  expect(screen.getByText(/DM Serif Display:400/)).toBeInTheDocument()   // provenance
})

test('revoca el blob URL al desmontar (cleanup)', () => {
  const { unmount } = render(<ComposeScreen result={result} onBack={() => {}} />)
  unmount()
  expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:svg')
})
