import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Dropzone } from './Dropzone'
import { EmptyState } from './EmptyState'

test('Dropzone dispara onUpload con el File elegido', async () => {
  const onUpload = vi.fn()
  const { container } = render(<Dropzone onUpload={onUpload} />)
  const input = container.querySelector('input[type=file]') as HTMLInputElement
  await userEvent.upload(input, new File(['d'], 'logo.png', { type: 'image/png' }))
  expect(onUpload).toHaveBeenCalledTimes(1)
  expect(onUpload.mock.calls[0][0]).toBeInstanceOf(File)
})

test('EmptyState enseña qué pasó y ofrece subir otro', () => {
  const onReset = vi.fn()
  render(<EmptyState onReset={onReset} />)
  expect(screen.getByText(/no encontramos texto/i)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /subir otro/i })).toBeInTheDocument()
})
