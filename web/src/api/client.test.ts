import { afterEach, expect, test, vi } from 'vitest'
import { analyze, compose, overlay, ApiError } from './client'

afterEach(() => { vi.restoreAllMocks() })

function mockFetch(status: number, body: unknown) {
  return vi.spyOn(globalThis, 'fetch').mockResolvedValue({
    ok: status >= 200 && status < 300, status,
    json: async () => body,
  } as Response)
}

test('analyze postea multipart a /api/analyze y devuelve el body', async () => {
  const f = mockFetch(200, { imageId: 'x', width: 10, height: 20, colorWarning: null, regions: [] })
  const resp = await analyze(new File(['d'], 'logo.png', { type: 'image/png' }))
  expect(resp.imageId).toBe('x')
  const [url, init] = f.mock.calls[0]
  expect(String(url)).toMatch(/\/api\/analyze$/)
  expect(init!.method).toBe('POST')
  expect(init!.body).toBeInstanceOf(FormData)
})

test('compose postea JSON sin contourSigma', async () => {
  const f = mockFetch(200, { svg: '<svg/>', provenance: [], ignoradas: [] })
  await compose({ imageId: 'x', choices: { '0': { family: 'Lora', wght: 400 } } })
  const init = f.mock.calls[0][1]!
  expect(init.method).toBe('POST')
  expect((init.headers as Record<string, string>)['Content-Type']).toBe('application/json')
  const sent = JSON.parse(init.body as string)
  expect(sent).toEqual({ imageId: 'x', choices: { '0': { family: 'Lora', wght: 400 } } })
  expect('contourSigma' in sent).toBe(false)
})

test('overlay postea JSON a /api/overlay', async () => {
  const f = mockFetch(200, { glyphs: [{ d: 'M0Z', transform: 'matrix(1)' }] })
  const r = await overlay({ imageId: 'x', regionIndex: 0, family: 'Lora', wght: 400 })
  expect(r.glyphs).toHaveLength(1)
  expect(String(f.mock.calls[0][0])).toMatch(/\/api\/overlay$/)
})

test('no-2xx con {detail:{error}} lanza ApiError tipado', async () => {
  mockFetch(422, { detail: { error: "peso 999 no disponible para 'Lora'" } })
  await expect(overlay({ imageId: 'x', regionIndex: 0, family: 'Lora', wght: 999 }))
    .rejects.toMatchObject({ name: 'ApiError', status: 422, message: expect.stringContaining('999') })
  expect(ApiError).toBeDefined()
})
