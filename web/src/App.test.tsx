import { render, screen } from '@testing-library/react'
import App from './App'

test('renderiza el shell con la marca', () => {
  render(<App />)
  expect(screen.getByText(/recompose/i)).toBeInTheDocument()
})
