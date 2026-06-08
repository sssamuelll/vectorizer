import { render, screen } from '@testing-library/react'
import { FlowTracker } from './FlowTracker'

test('renderiza los 4 pasos del flujo', () => {
  render(<FlowTracker phase="idle" />)
  for (const label of ['Subir', 'Analizar', 'Elegir', 'Componer']) {
    expect(screen.getByText(label)).toBeInTheDocument()
  }
})

test('marca el paso activo según la fase', () => {
  const { container } = render(<FlowTracker phase="choosing" />)
  const items = container.querySelectorAll('ol li')
  expect(items).toHaveLength(4)
  // choosing → "Elegir" (índice 2) es el activo; los previos van con ✓
  expect(items[0].textContent).toContain('✓')   // Subir hecho
  expect(items[1].textContent).toContain('✓')   // Analizar hecho
  expect(items[2].textContent).toContain('›')   // Elegir activo
  expect(items[3].textContent).toContain('·')   // Componer pendiente
})
