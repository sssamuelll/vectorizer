# Spec C1a — Frontend Walking Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the React+Vite+TypeScript+CSS-puro frontend happy path — upload → analyze → resolve each tie region by a faithful magenta overlay over the uploaded raster → compose → download — wired to the real backend (`/api/analyze`, `/api/compose`, `/api/overlay`).

**Architecture:** A `web/` Vite app. A typed client mirrors the Pydantic DTOs (`RegionDTO` as a discriminated union on `decision`). A pure `useReducer` state machine routes post-analyze by the shape of the result (empty / choosing / ready), gates download over tie regions, and keeps an `imageId`-scoped overlay cache. The judgment surface is an `<img>` of the upload plus a coordinate-registered `<svg>` overlay that paints only the active region's candidate glyphs in magenta. The composed SVG is rendered isolated (blob `<img>`) so its global `<style>` cannot leak.

**Tech Stack:** React (whatever `npm create vite@latest --template react-ts` installs today — currently React 19 + TS 6 + Vite 8 + Vitest 4; no plan code is React-18-only), Vite, TypeScript, CSS puro (no Tailwind, no component lib, no state lib), Vitest + React Testing Library + jsdom. Note: under React 19 `StrictMode` (in `main.tsx`), effects double-invoke in dev — the analyze/prefetch effects are idempotent here (the `reqSeq` guard drops the stale `ANALYZED`, the overlay cache dedups), so this is benign; the Vitest tests render `<App/>` without `StrictMode`, so they do not double-fire.

**Spec:** `docs/superpowers/specs/2026-06-08-recompose-web-skeleton-design.md`

**Prototype reference (visual port source):** the design team's prototype, extractable from `C:\Users\simon\Desktop\vectorizer.zip` (also at `C:\Users\simon\AppData\Local\Temp\vzdesign\`). Files: `judgment.jsx`, `app.jsx`, `states.jsx`, `data.jsx`, `styles.css`, `README.md`. Port markup/classes/microcopy from these; do NOT copy the mock data or the scenario chrome.

**Git safety (all tasks):** Subagents share the controller's working tree and branch (`recompose-web-skeleton`). Do NOT run `git checkout`, `git switch`, `git reset`, or `git stash`. Only `git add` / `git commit` of the files listed per task. All `npm` commands run inside `web/`.

**Backend for live tests:** the contract/manual tests need the backend running: from the repo root, `python -m server` (serves `127.0.0.1:8000`). Vitest unit tests do NOT need it (fetch is mocked); the contract test skips if it is down.

---

## Tasks

### Task 1: Scaffold `web/` (Vite + React + TS + Vitest) + ported stylesheet + smoke test

**Files:**
- Create: `web/` (Vite scaffold), `web/vite.config.ts`, `web/src/test/setup.ts`, `web/src/styles.css`, `web/src/App.tsx`, `web/src/main.tsx`, `web/index.html`
- Test: `web/src/App.test.tsx`

- [ ] **Step 1: Scaffold and install**

From the repo root run:
```bash
npm create vite@latest web -- --template react-ts
cd web
npm install
npm install -D vitest @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom
```
Delete the generated boilerplate that we replace: `web/src/App.css`, `web/src/assets/`, and the contents of `web/src/index.css` (leave the file empty or remove its import).

- [ ] **Step 2: Configure Vitest**

Replace `web/vite.config.ts` with (import `defineConfig` from `vitest/config`, NOT `vite` — under Vitest 4 the `test` key is not on `vite`'s `UserConfig`, and the `/// <reference types="vitest" />` triple-slash is no longer sufficient; `tsc -b` type-checks this file via `tsconfig.node.json`):
```ts
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.ts',
  },
})
```
Create `web/src/test/setup.ts`:
```ts
import '@testing-library/jest-dom'
```
**Add the test globals to TypeScript** — the template's `tsconfig.app.json` has `"include": ["src"]` (so `tsc -b` type-checks every `*.test.tsx`) and `"types": ["vite/client"]` only. Test files use bare `test`/`expect`/`vi`/`beforeAll` (relying on `globals:true`) — without the global types, `tsc -b` fails with `Cannot find name 'test'`/`'expect'`/`'vi'` (≈28 errors). In `web/tsconfig.app.json`, set:
```jsonc
"compilerOptions": { /* ...existing... */ "types": ["vite/client", "vitest/globals"] }
```
(The jest-dom matchers `toBeInTheDocument`/`toBeDisabled`/`toBeEnabled` come from the `import '@testing-library/jest-dom'` in `setup.ts`.)

Add to `web/package.json` "scripts": `"test": "vitest run"`, `"test:watch": "vitest"`.

- [ ] **Step 3: Bring in the ported stylesheet and a minimal shell**

Extract `styles.css` from the prototype into `web/src/styles.css` (from `C:\Users\simon\AppData\Local\Temp\vzdesign\styles.css`; if absent, extract `vectorizer.zip`). Keep the `:root` oklch tokens and the structural classes (`.app`, `.topbar`, `.body`, `.rail`, `.main`, `.anchor`, `.rule`, `.cand-zone`, `.cand-rail`, `.cand`, `.btn`, `.panel`, `.compose`, `.dropzone`, `.banner`, `.region-row`, `.badge`, etc.). **Critical (spec §3): the anchor image must NOT have a `max-height` or independent height constraint.** If the ported `.anchor`/image rules carry one, remove it for the anchor image specifically.

Replace `web/src/main.tsx`:
```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './styles.css'

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>)
```
Replace `web/src/App.tsx` with a minimal shell:
```tsx
export default function App() {
  return (
    <div className="app">
      <div className="topbar"><span className="brand">recompose<span className="dot">.</span></span></div>
      <div className="body"><div className="main" /></div>
    </div>
  )
}
```

- [ ] **Step 4: Write the smoke test**

`web/src/App.test.tsx`:
```tsx
import { render, screen } from '@testing-library/react'
import App from './App'

test('renderiza el shell con la marca', () => {
  render(<App />)
  expect(screen.getByText(/recompose/i)).toBeInTheDocument()
})
```

- [ ] **Step 5: Run tests + build**

Run: `cd web && npm test`
Expected: 1 passed.
Run: `cd web && npm run build`
Expected: tsc + vite build succeed (no type errors).

- [ ] **Step 6: Commit**

```bash
git add web/ -- ':!web/node_modules'
git commit -m "feat(web): scaffold Vite+React+TS+Vitest + styles porteados + smoke" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```
Ensure `web/node_modules/` is git-ignored (the Vite template adds a `web/.gitignore` with `node_modules`). Verify with `git status` that `node_modules` is not staged.

---

### Task 2: Types (`types.ts`) + client (`client.ts`) + tests

**Files:**
- Create: `web/src/api/types.ts`, `web/src/api/client.ts`
- Test: `web/src/api/client.test.ts`, `web/src/api/contract.test.ts`

- [ ] **Step 1: Write `types.ts` (discriminated union)**

`web/src/api/types.ts` — hand mirror of `server/models.py`; `Region` is discriminated on `decision`:
```ts
// Espejo de server/models.py. RegionDTO = unión discriminada sobre `decision`.
export type Choice = { family: string; wght: number }            // ChoiceDTO
export type RankEntry = { family: string; wght: number; score: number; tie: boolean }  // RankEntryDTO; score/tie NO se muestran (regla 5)
export type Bbox = [number, number, number, number]
type RegionBase = { index: number; bbox: Bbox; text: string; classification: string; classScore: number }
export type Region =
  | (RegionBase & { decision: 'tie'; candidates: RankEntry[] })
  | (RegionBase & { decision: 'leader'; chosen: Choice })
  | (RegionBase & { decision: 'no_font'; reason: string })
  | (RegionBase & { decision: 'vectorized'; reason: string })
export type AnalyzeResponse = {
  imageId: string; width: number; height: number; colorWarning: string | null; regions: Region[]
}
export type GlyphPath = { d: string; transform: string }          // GlyphPath
export type OverlayResponse = { glyphs: GlyphPath[] }              // OverlayResponse
export type OverlayRequest = { imageId: string; regionIndex: number; family: string; wght: number }
export type ComposeRequest = { imageId: string; choices: Record<string, Choice> }  // contourSigma omitido → default server
export type IndexText = { index: number; text: string }
export type ComposeResponse = { svg: string; provenance: string[]; ignoradas: IndexText[] }
```

- [ ] **Step 2: Write the failing client tests**

`web/src/api/client.test.ts`:
```ts
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
```

- [ ] **Step 3: Run to verify failure**

Run: `cd web && npx vitest run src/api/client.test.ts`
Expected: FAIL — cannot resolve `./client`.

- [ ] **Step 4: Implement `client.ts`**

`web/src/api/client.ts`:
```ts
import type { AnalyzeResponse, ComposeRequest, ComposeResponse, OverlayRequest, OverlayResponse } from './types'

const BASE = (import.meta.env.VITE_API_BASE as string) || 'http://127.0.0.1:8000'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.name = 'ApiError'; this.status = status }
}

async function parseError(res: Response): Promise<never> {
  let msg = `HTTP ${res.status}`
  try {
    const body = await res.json()
    if (body?.detail?.error) msg = body.detail.error
    else if (typeof body?.detail === 'string') msg = body.detail
  } catch { /* keep default */ }
  throw new ApiError(res.status, msg)
}

export async function analyze(file: File): Promise<AnalyzeResponse> {
  const fd = new FormData(); fd.append('file', file)
  const res = await fetch(`${BASE}/api/analyze`, { method: 'POST', body: fd })
  if (!res.ok) return parseError(res)
  return res.json()
}

export async function compose(req: ComposeRequest): Promise<ComposeResponse> {
  const res = await fetch(`${BASE}/api/compose`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(req) })
  if (!res.ok) return parseError(res)
  return res.json()
}

export async function overlay(req: OverlayRequest): Promise<OverlayResponse> {
  const res = await fetch(`${BASE}/api/overlay`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(req) })
  if (!res.ok) return parseError(res)
  return res.json()
}

export const API_BASE = BASE
```

- [ ] **Step 5: Write the contract test (gated, trimmed to C1a's fields)**

`web/src/api/contract.test.ts`:
```ts
import { expect, test } from 'vitest'
import { API_BASE } from './client'

// Verifica que los campos que C1a lee/escribe existen en el OpenAPI vivo.
// Skip si el backend no responde (no rompe la suite offline).
async function openapi(): Promise<any | null> {
  try {
    const res = await fetch(`${API_BASE}/openapi.json`)
    if (!res.ok) return null
    return await res.json()
  } catch { return null }
}

test('el contrato del backend cubre los campos que C1a usa', async () => {
  const spec = await openapi()
  if (!spec) { console.warn('backend no disponible; contrato omitido'); return }
  const props = (name: string) => Object.keys(spec.components?.schemas?.[name]?.properties ?? {})
  expect(props('RegionDTO')).toEqual(expect.arrayContaining(
    ['index', 'bbox', 'text', 'classification', 'classScore', 'decision', 'candidates', 'chosen', 'reason']))
  expect(props('AnalyzeResponse')).toEqual(expect.arrayContaining(
    ['imageId', 'width', 'height', 'colorWarning', 'regions']))
  expect(props('OverlayResponse')).toEqual(expect.arrayContaining(['glyphs']))
  expect(props('GlyphPath')).toEqual(expect.arrayContaining(['d', 'transform']))
  expect(props('OverlayRequest')).toEqual(expect.arrayContaining(['imageId', 'regionIndex', 'family', 'wght']))
  expect(props('ComposeResponse')).toEqual(expect.arrayContaining(['svg', 'provenance', 'ignoradas']))
})
```

- [ ] **Step 6: Run tests**

Run: `cd web && npx vitest run src/api/`
Expected: client tests PASS; the contract test PASSES if the backend is running (`python -m server`), else logs "backend no disponible" and passes (no assertions hit).

- [ ] **Step 7: Commit**

```bash
git add web/src/api/
git commit -m "feat(web): types (RegionDTO union discriminada) + client + contrato" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: State machine (`state/useApp.ts`) — pure reducer: routing, gate, cursor, integrity, errors

**Files:**
- Create: `web/src/state/useApp.ts` (reducer + helpers exported; the hook is added in Task 8)
- Test: `web/src/state/reducer.test.ts`

- [ ] **Step 1: Write the failing reducer tests**

`web/src/state/reducer.test.ts`:
```ts
import { expect, test } from 'vitest'
import { reducer, initialState, isComplete, cacheKey, type AppState } from './useApp'
import type { AnalyzeResponse, Region } from '../api/types'

const tie = (index: number): Region => ({
  index, bbox: [0, 0, 10, 10], text: 't', classification: 'type', classScore: 0.9,
  decision: 'tie', candidates: [{ family: 'A', wght: 400, score: 0.8, tie: false },
                                { family: 'B', wght: 400, score: 0.79, tie: true }] })
const leader = (index: number): Region => ({
  index, bbox: [0, 0, 10, 10], text: 'l', classification: 'type', classScore: 0.9,
  decision: 'leader', chosen: { family: 'Lora', wght: 400 } })
const vector = (index: number): Region => ({
  index, bbox: [0, 0, 10, 10], text: '—', classification: 'handwriting', classScore: 0.2,
  decision: 'vectorized', reason: 'trazo' })
const resp = (regions: Region[]): AnalyzeResponse =>
  ({ imageId: 'img1', width: 100, height: 50, colorWarning: null, regions })

const afterUpload = (): AppState =>
  reducer(initialState, { type: 'UPLOAD', file: new File(['d'], 'x.png'), objectURL: 'blob:1' })

test('ANALYZED con 0 regiones recomponibles → empty', () => {
  const s = reducer(afterUpload(), { type: 'ANALYZED', resp: resp([vector(0)]), seq: 1 })
  expect(s.phase).toBe('empty')
})

test('ANALYZED con ties → choosing + primera tie activa', () => {
  const s = reducer(afterUpload(), { type: 'ANALYZED', resp: resp([leader(0), tie(1), tie(2)]), seq: 1 })
  expect(s.phase).toBe('choosing')
  expect(s.activeRegion).toBe(1)
  expect(isComplete(s)).toBe(false)
})

test('ANALYZED recomponible sin ties (todo leader) → choosing, activeRegion null, complete', () => {
  const s = reducer(afterUpload(), { type: 'ANALYZED', resp: resp([leader(0)]), seq: 1 })
  expect(s.phase).toBe('choosing')
  expect(s.activeRegion).toBeNull()
  expect(isComplete(s)).toBe(true)
})

test('ANALYZED con seq viejo se descarta (stale)', () => {
  const base = afterUpload()                                  // reqSeq = 1
  const s = reducer(base, { type: 'ANALYZED', resp: resp([tie(0)]), seq: 0 })
  expect(s).toBe(base)
})

test('gate complete: true solo cuando toda tie tiene elección', () => {
  let s = reducer(afterUpload(), { type: 'ANALYZED', resp: resp([tie(0), tie(1)]), seq: 1 })
  expect(isComplete(s)).toBe(false)
  s = reducer(s, { type: 'CHOOSE', index: 0, choice: { family: 'A', wght: 400 } })
  expect(isComplete(s)).toBe(false)               // falta la 1
  expect(s.activeRegion).toBe(1)                  // avanzó a la siguiente tie
  s = reducer(s, { type: 'CHOOSE', index: 1, choice: { family: 'A', wght: 400 } })
  expect(isComplete(s)).toBe(true)
  expect(s.activeRegion).toBeNull()               // no quedan ties
})

test('SET_ACTIVE limpia armed (invariante de cursor)', () => {
  let s = reducer(afterUpload(), { type: 'ANALYZED', resp: resp([tie(0), tie(1)]), seq: 1 })
  s = reducer(s, { type: 'ARM', choice: { family: 'A', wght: 400 } })
  expect(s.armed).not.toBeNull()
  s = reducer(s, { type: 'SET_ACTIVE', index: 1 })
  expect(s.armed).toBeNull()
  expect(s.activeRegion).toBe(1)
})

test('OVERLAY_FETCHED con imageId viejo se descarta', () => {
  const s0 = reducer(afterUpload(), { type: 'ANALYZED', resp: resp([tie(0)]), seq: 1 })
  const s1 = reducer(s0, { type: 'OVERLAY_FETCHED', key: 'k', glyphs: [{ d: 'M', transform: 't' }], imageId: 'OTRO' })
  expect(s1.overlayCache.size).toBe(0)
  const s2 = reducer(s0, { type: 'OVERLAY_FETCHED', key: cacheKey('img1', 0, { family: 'A', wght: 400 }), glyphs: [{ d: 'M', transform: 't' }], imageId: 'img1' })
  expect(s2.overlayCache.size).toBe(1)
})

test('cacheKey incluye imageId', () => {
  expect(cacheKey('img1', 0, { family: 'A', wght: 400 })).toBe('img1|0|A|400')
})

test('FAIL analyze → retry vuelve a idle; compose → choosing; 404 → idle limpio', () => {
  let s = reducer(afterUpload(), { type: 'ANALYZED', resp: resp([tie(0)]), seq: 1 })
  // compose-fail
  let e = reducer({ ...s, phase: 'composing' }, { type: 'FAIL', status: 503, message: 'down', origin: 'compose' })
  expect(e.phase).toBe('error')
  expect(reducer(e, { type: 'RETRY' }).phase).toBe('choosing')
  // analyze-fail
  let a = reducer(afterUpload(), { type: 'FAIL', status: 0, message: 'net', origin: 'analyze' })
  expect(reducer(a, { type: 'RETRY' }).phase).toBe('idle')
  // 404 (sesión muerta) → idle limpio sin analysis
  let f = reducer(e, { type: 'FAIL', status: 404, message: 'imageId desconocido', origin: 'compose' })
  const r = reducer(f, { type: 'RETRY' })
  expect(r.phase).toBe('idle')
  expect(r.analysis).toBeNull()
})

test('RESET vacía choices/analysis e incrementa reqSeq', () => {
  let s = reducer(afterUpload(), { type: 'ANALYZED', resp: resp([tie(0)]), seq: 1 })
  s = reducer(s, { type: 'CHOOSE', index: 0, choice: { family: 'A', wght: 400 } })
  const r = reducer(s, { type: 'RESET' })
  expect(r.analysis).toBeNull()
  expect(Object.keys(r.choices)).toHaveLength(0)
  expect(r.reqSeq).toBe(s.reqSeq + 1)
})
```

- [ ] **Step 2: Run to verify failure**

Run: `cd web && npx vitest run src/state/reducer.test.ts`
Expected: FAIL — cannot resolve `./useApp`.

- [ ] **Step 3: Implement the reducer + helpers in `useApp.ts`**

`web/src/state/useApp.ts` (the hook with effects is added in Task 8; here only the pure parts, all exported):
```ts
import type { AnalyzeResponse, Choice, ComposeResponse, GlyphPath, Region } from '../api/types'

export type Phase = 'idle' | 'analyzing' | 'choosing' | 'empty' | 'composing' | 'done' | 'error'
export type ErrorOrigin = 'analyze' | 'compose'
export type AppError = { status: number; message: string; origin: ErrorOrigin }

export interface AppState {
  phase: Phase
  file: File | null
  objectURL: string | null
  analysis: AnalyzeResponse | null
  choices: Record<number, Choice>
  activeRegion: number | null
  armed: Choice | null
  overlayCache: Map<string, GlyphPath[]>
  result: ComposeResponse | null
  error: AppError | null
  reqSeq: number
}

export type Action =
  | { type: 'UPLOAD'; file: File; objectURL: string }
  | { type: 'ANALYZED'; resp: AnalyzeResponse; seq: number }
  | { type: 'SET_ACTIVE'; index: number }
  | { type: 'ARM'; choice: Choice | null }
  | { type: 'CHOOSE'; index: number; choice: Choice }
  | { type: 'OVERLAY_FETCHED'; key: string; glyphs: GlyphPath[]; imageId: string }
  | { type: 'COMPOSING' }
  | { type: 'COMPOSED'; resp: ComposeResponse }
  | { type: 'FAIL'; status: number; message: string; origin: ErrorOrigin }
  | { type: 'RETRY' }
  | { type: 'RESET' }

export const initialState: AppState = {
  phase: 'idle', file: null, objectURL: null, analysis: null, choices: {},
  activeRegion: null, armed: null, overlayCache: new Map(), result: null, error: null, reqSeq: 0,
}

export const cacheKey = (imageId: string, region: number, c: Choice) => `${imageId}|${region}|${c.family}|${c.wght}`
const recomposable = (r: Region) => r.decision === 'tie' || r.decision === 'leader'
const requiresDecision = (r: Region) => r.decision === 'tie'
export const isComplete = (s: AppState) =>
  !!s.analysis && s.analysis.regions.filter(requiresDecision).every(r => r.index in s.choices)

export function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'UPLOAD':
      return { ...initialState, overlayCache: new Map(), phase: 'analyzing',
               file: action.file, objectURL: action.objectURL, reqSeq: state.reqSeq + 1 }
    case 'ANALYZED': {
      if (action.seq !== state.reqSeq) return state
      const regs = action.resp.regions
      if (!regs.some(recomposable)) return { ...state, phase: 'empty', analysis: action.resp }
      const firstTie = regs.find(requiresDecision)
      return { ...state, phase: 'choosing', analysis: action.resp,
               activeRegion: firstTie ? firstTie.index : null }
    }
    case 'SET_ACTIVE':
      return { ...state, activeRegion: action.index, armed: null }
    case 'ARM':
      return { ...state, armed: action.choice }
    case 'CHOOSE': {
      const choices = { ...state.choices, [action.index]: action.choice }
      const regs = state.analysis?.regions ?? []
      const nextTie = regs.find(r => requiresDecision(r) && !(r.index in choices))
      return { ...state, choices, armed: null, activeRegion: nextTie ? nextTie.index : null }
    }
    case 'OVERLAY_FETCHED': {
      if (!state.analysis || action.imageId !== state.analysis.imageId) return state
      const cache = new Map(state.overlayCache); cache.set(action.key, action.glyphs)
      return { ...state, overlayCache: cache }
    }
    case 'COMPOSING':
      return state.phase === 'composing' ? state : { ...state, phase: 'composing' }
    case 'COMPOSED':
      return { ...state, phase: 'done', result: action.resp }
    case 'FAIL':
      return { ...state, phase: 'error', error: { status: action.status, message: action.message, origin: action.origin } }
    case 'RETRY': {
      if (!state.error) return state
      if (state.error.status === 404) return { ...initialState, reqSeq: state.reqSeq + 1 }
      if (state.error.origin === 'compose') return { ...state, phase: 'choosing', error: null }
      return { ...state, phase: 'idle', error: null }
    }
    case 'RESET':
      return { ...initialState, overlayCache: new Map(), reqSeq: state.reqSeq + 1 }
    default:
      return state
  }
}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd web && npx vitest run src/state/reducer.test.ts`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/state/
git commit -m "feat(web): reducer puro — routing por forma, gate, cursor, integridad, errores" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: `Anchor.tsx` — the coordinate-registered judgment surface (risk piece)

**Files:**
- Create: `web/src/components/Anchor.tsx`
- Test: `web/src/components/Anchor.test.tsx`

- [ ] **Step 1: Write the failing test**

`web/src/components/Anchor.test.tsx`:
```tsx
import { render } from '@testing-library/react'
import { Anchor } from './Anchor'

const glyphs = [{ d: 'M0 0Z', transform: 'matrix(1 0 0 1 0 0)' },
                { d: 'M1 1Z', transform: 'matrix(1 0 0 1 5 0)' }]

test('el SVG usa viewBox natural + preserveAspectRatio meet y pinta los glifos en magenta', () => {
  const { container } = render(
    <Anchor imageUrl="blob:1" width={300} height={120} glyphs={glyphs} showOverlay />)
  const svg = container.querySelector('svg.overlay-layer')!
  expect(svg.getAttribute('viewBox')).toBe('0 0 300 120')
  expect(svg.getAttribute('preserveAspectRatio')).toBe('xMidYMid meet')
  const g = svg.querySelector('g')!
  expect(g.getAttribute('fill')).toBe('var(--magenta)')
  const paths = svg.querySelectorAll('path')
  expect(paths).toHaveLength(2)
  expect(paths[1].getAttribute('transform')).toBe('matrix(1 0 0 1 5 0)')
})

test('la <img> lleva image-orientation:none', () => {
  const { container } = render(<Anchor imageUrl="blob:1" width={10} height={10} glyphs={null} showOverlay />)
  const img = container.querySelector('img.anchor-img') as HTMLImageElement
  expect(img.style.imageOrientation).toBe('none')   // lee del CSSStyleDeclaration vivo (robusto vs serialización)
})

test('showOverlay=false oculta la capa', () => {
  const { container } = render(
    <Anchor imageUrl="blob:1" width={10} height={10} glyphs={glyphs} showOverlay={false} />)
  const svg = container.querySelector('svg.overlay-layer') as SVGElement
  expect(svg.style.visibility).toBe('hidden')
})
```

- [ ] **Step 2: Run to verify failure**

Run: `cd web && npx vitest run src/components/Anchor.test.tsx`
Expected: FAIL — cannot resolve `./Anchor`.

- [ ] **Step 3: Implement `Anchor.tsx`**

```tsx
import type { GlyphPath } from '../api/types'

export function Anchor({ imageUrl, width, height, glyphs, showOverlay }: {
  imageUrl: string; width: number; height: number; glyphs: GlyphPath[] | null; showOverlay: boolean
}) {
  return (
    <div className="anchor-box" style={{ position: 'relative', display: 'inline-block',
                                         background: '#fff', maxWidth: '100%' }}>
      <img className="anchor-img" src={imageUrl} alt="logo original"
           style={{ display: 'block', width: '100%', height: 'auto', imageOrientation: 'none' as never }} />
      <svg className="overlay-layer" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="xMidYMid meet"
           style={{ position: 'absolute', inset: 0, width: '100%', height: '100%',
                    visibility: showOverlay ? 'visible' : 'hidden', pointerEvents: 'none' }}
           aria-hidden={!showOverlay}>
        {glyphs && <g fill="var(--magenta)">{glyphs.map((g, i) => <path key={i} d={g.d} transform={g.transform} />)}</g>}
      </svg>
    </div>
  )
}
```
The inline `image-orientation:none` (spec §3, EXIF) plus the white background (RGBA composite) plus the shared box (`<img>` defines size, `<svg>` is `inset:0` of the same `position:relative` box) are the coordinate invariant. Do NOT add `max-height`/`object-fit`/border to `.anchor-img`.

- [ ] **Step 4: Run to verify pass**

Run: `cd web && npx vitest run src/components/Anchor.test.tsx`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/components/Anchor.tsx web/src/components/Anchor.test.tsx
git commit -m "feat(web): Anchor — capa SVG registrada a coordenadas, active-only, EXIF none" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: `CandidateRail.tsx` — candidate cards (hover arms, click chooses)

**Files:**
- Create: `web/src/components/CandidateRail.tsx`
- Test: `web/src/components/CandidateRail.test.tsx`

Visual port reference: prototype `judgment.jsx` `CandidateRail`/`Candidate` (lines 63–125). C1a difference: NO `cand.css` webfont on the label (neutral sans), NO score, and NO "otra familia" hatch (that is C1b).

- [ ] **Step 1: Write the failing test**

`web/src/components/CandidateRail.test.tsx`:
```tsx
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
```

- [ ] **Step 2: Run to verify failure**

Run: `cd web && npx vitest run src/components/CandidateRail.test.tsx`
Expected: FAIL — cannot resolve `./CandidateRail`.

- [ ] **Step 3: Implement `CandidateRail.tsx`**

```tsx
import type { Choice, RankEntry } from '../api/types'

export function CandidateRail({ text, candidates, chosen, armed, onArm, onChoose }: {
  text: string; candidates: RankEntry[]; chosen: Choice | null; armed: Choice | null
  onArm: (c: Choice | null) => void; onChoose: (c: Choice) => void
}) {
  return (
    <div className="cand-zone">
      <div className="row"><span className="t">Candidatas para «{text}»</span></div>
      <div className="cand-rail">
        {candidates.map((c, i) => {
          const choice: Choice = { family: c.family, wght: c.wght }
          const isChosen = !!chosen && chosen.family === c.family && chosen.wght === c.wght
          const isArmed = !!armed && armed.family === c.family && armed.wght === c.wght
          return (
            <button key={i} className={'cand ' + (isChosen ? 'chosen ' : '') + (isArmed && !isChosen ? 'armed' : '')}
                    onMouseEnter={() => onArm(choice)} onMouseLeave={() => onArm(null)}
                    onFocus={() => onArm(choice)} onBlur={() => onArm(null)}
                    onClick={() => onChoose(choice)}>
              <span className="fam">{c.family}</span>
              <span className="hint">{isChosen ? 'elegida ✓' : c.wght}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd web && npx vitest run src/components/CandidateRail.test.tsx`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/components/CandidateRail.tsx web/src/components/CandidateRail.test.tsx
git commit -m "feat(web): CandidateRail — tarjetas familia+peso, hover arma, clic elige" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: `Rail.tsx` (4 badges + counter + gate) + flow screens (Dropzone, Analyzing, EmptyState)

**Files:**
- Create: `web/src/components/Rail.tsx`, `web/src/components/Dropzone.tsx`, `web/src/components/Analyzing.tsx`, `web/src/components/EmptyState.tsx`
- Test: `web/src/components/Rail.test.tsx`, `web/src/components/flow.test.tsx`

Visual port reference: `app.jsx` `FlowTracker`/`RegionList`/`badgeFor` and `states.jsx` `Dropzone`/`Analyzing`/`EmptyState`.

- [ ] **Step 1: Write the failing tests**

`web/src/components/Rail.test.tsx`:
```tsx
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
```

`web/src/components/flow.test.tsx`:
```tsx
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
```

- [ ] **Step 2: Run to verify failure**

Run: `cd web && npx vitest run src/components/Rail.test.tsx src/components/flow.test.tsx`
Expected: FAIL — modules unresolved.

- [ ] **Step 3: Implement the components**

`web/src/components/Rail.tsx`:
```tsx
import type { Choice, Region } from '../api/types'

const BADGE: Record<Region['decision'], [string, string]> = {
  tie: ['tie', 'empate'], leader: ['leader', 'líder'],
  vectorized: ['vector', 'vectorizado'], no_font: ['nofont', 'sin fuente'],
}

export function Rail({ regions, active, choices, complete, doneCount, tieCount, onPick, onDownload }: {
  regions: Region[]; active: number | null; choices: Record<number, Choice>
  complete: boolean; doneCount: number; tieCount: number
  onPick: (i: number) => void; onDownload: () => void
}) {
  return (
    <div className="rail">
      <p className="lbl">Regiones detectadas</p>
      <div className="regions">
        {regions.map(r => {
          const chosen = choices[r.index]
          const [cls, txt] = chosen ? ['done', 'elegida'] : BADGE[r.decision]
          const meta = chosen ? chosen.family
            : r.decision === 'tie' ? `${r.candidates.length} candidatas`
            : r.decision === 'vectorized' ? 'se dibuja tal cual'
            : r.decision === 'leader' ? r.chosen.family : 'sin candidatas'  // no_font meta ≠ badge label
          return (
            <button key={r.index} className={'region-row ' + (r.index === active ? 'active ' : '') + (chosen ? 'done' : '')}
                    onClick={() => onPick(r.index)}>
              <span className="idx">{String(r.index).padStart(2, '0')}</span>
              <span><span className="rtext">{r.decision === 'vectorized' ? 'trazo caligráfico' : r.text}</span>
                    <span className="rmeta">{meta}</span></span>
              <span className={'badge ' + cls}>{txt}</span>
            </button>
          )
        })}
      </div>
      <div className="foot">
        <p className="counter"><b>{doneCount}</b> de <b>{tieCount}</b> elegidas</p>
        <button className="btn block" disabled={!complete} onClick={onDownload}>Descargar SVG</button>
      </div>
    </div>
  )
}
```
`web/src/components/Dropzone.tsx`:
```tsx
import { useRef } from 'react'

export function Dropzone({ onUpload }: { onUpload: (f: File) => void }) {
  const ref = useRef<HTMLInputElement>(null)
  const pick = (files: FileList | null) => { if (files && files[0]) onUpload(files[0]) }
  return (
    <div className="dropzone" onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); pick(e.dataTransfer.files) }}>
      <p className="big">Suelta el logo aquí</p>
      <p className="sub">Una imagen de un logo de una sola tinta. La vectorizamos, encontramos el texto y lo rehacemos con la fuente real.</p>
      <input ref={ref} type="file" accept="image/*" style={{ display: 'none' }} onChange={e => pick(e.target.files)} />
      <button className="btn" onClick={() => ref.current?.click()}>Elegir imagen…</button>
    </div>
  )
}
```
`web/src/components/Analyzing.tsx`:
```tsx
export function Analyzing({ file }: { file: string }) {
  return (
    <div className="analyzing"><div className="inner">
      <p className="eyebrow">Analizando</p>
      <h1 style={{ fontSize: 20, fontWeight: 600, margin: 0 }}>Leyendo {file}</h1>
      <div className="scan-bar"><i /></div>
    </div></div>
  )
}
```
`web/src/components/EmptyState.tsx`:
```tsx
export function EmptyState({ onReset }: { onReset: () => void }) {
  return (
    <div className="panel"><div className="inner">
      <div className="ico">∅</div>
      <h2>No encontramos texto para recomponer</h2>
      <p>Analizamos la imagen y no detectamos regiones de texto tipográfico. Recompose existe para reemplazar texto pixelado por su fuente real; sin texto, no hay nada que rehacer.</p>
      <div className="actions"><button className="btn" onClick={onReset}>Subir otro logo</button></div>
    </div></div>
  )
}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd web && npx vitest run src/components/Rail.test.tsx src/components/flow.test.tsx`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/components/Rail.tsx web/src/components/Dropzone.tsx web/src/components/Analyzing.tsx web/src/components/EmptyState.tsx web/src/components/Rail.test.tsx web/src/components/flow.test.tsx
git commit -m "feat(web): Rail con badges para las 4 decisiones + Dropzone/Analyzing/EmptyState" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: `ComposeScreen.tsx` — isolated SVG render + download

**Files:**
- Create: `web/src/components/ComposeScreen.tsx`
- Test: `web/src/components/ComposeScreen.test.tsx`

The composed SVG is rendered as a blob `<img>`, NOT injected into the app DOM — its global `<style>` (`.ink`/`.type`) must not leak into the app (junta finding). The same blob URL is the download href.

- [ ] **Step 1: Write the failing test**

`web/src/components/ComposeScreen.test.tsx`:
```tsx
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
```

- [ ] **Step 2: Run to verify failure**

Run: `cd web && npx vitest run src/components/ComposeScreen.test.tsx`
Expected: FAIL — cannot resolve `./ComposeScreen`.

- [ ] **Step 3: Implement `ComposeScreen.tsx`**

```tsx
import { useEffect, useMemo } from 'react'
import type { ComposeResponse } from '../api/types'

export function ComposeScreen({ result, onBack }: { result: ComposeResponse; onBack: () => void }) {
  const blobUrl = useMemo(
    () => URL.createObjectURL(new Blob([result.svg], { type: 'image/svg+xml' })), [result.svg])
  useEffect(() => () => URL.revokeObjectURL(blobUrl), [blobUrl])
  return (
    <div className="compose"><div className="inner">
      <p className="eyebrow">Listo</p>
      <h1 style={{ fontSize: 20, fontWeight: 600, margin: 0 }}>Tu SVG está armado</h1>
      <div className="svg-frame"><img src={blobUrl} alt="SVG recompuesto" style={{ maxWidth: '100%' }} /></div>
      <pre className="provenance">{result.provenance.join('\n')}</pre>
      <div className="actions">
        <a className="btn" href={blobUrl} download="recompose.svg">Descargar SVG</a>
        <button className="btn ghost" onClick={onBack}>Volver a la elección</button>
      </div>
    </div></div>
  )
}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd web && npx vitest run src/components/ComposeScreen.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/components/ComposeScreen.tsx web/src/components/ComposeScreen.test.tsx
git commit -m "feat(web): ComposeScreen — render SVG aislado (blob img) + descarga" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 8: `App.tsx` + the `useApp` hook (effects) — wiring + integration test

**Files:**
- Modify: `web/src/state/useApp.ts` (append the `useApp` hook with effects), `web/src/App.tsx` (the full shell + ChooseScreen + phase routing)
- Create: `web/src/components/ChooseScreen.tsx`
- Test: `web/src/App.test.tsx` (replace the smoke test with the integration test)

- [ ] **Step 1: Write the failing integration test**

Replace `web/src/App.test.tsx`:
```tsx
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
```

- [ ] **Step 2: Run to verify failure**

Run: `cd web && npx vitest run src/App.test.tsx`
Expected: FAIL — `ChooseScreen` unresolved / `useApp` not exported / App is the bare shell.

- [ ] **Step 3: Add the `useApp` hook to `useApp.ts`**

Move these two `import`s to the TOP of `web/src/state/useApp.ts` (next to the existing `import type { ... } from '../api/types'`), then append the `useApp` function below the reducer:
```ts
// (top of file, with the other imports)
import { useEffect, useReducer, useRef } from 'react'
import * as api from '../api/client'
```
```ts
// (appended below the reducer)
export function useApp() {
  const [state, dispatch] = useReducer(reducer, initialState)
  const ref = useRef(state); ref.current = state

  // analyze al entrar a 'analyzing'
  useEffect(() => {
    if (state.phase !== 'analyzing' || !state.file) return
    const seq = state.reqSeq; let live = true
    api.analyze(state.file)
      .then(resp => { if (live) dispatch({ type: 'ANALYZED', resp, seq }) })
      .catch(e => { if (live) dispatch({ type: 'FAIL', status: e?.status ?? 0, message: e?.message ?? 'error', origin: 'analyze' }) })
    return () => { live = false }
  }, [state.phase, state.reqSeq])

  // console.warn del colorWarning (banner visible = C1b)
  useEffect(() => {
    if (state.phase !== 'choosing' && state.phase !== 'empty') return
    if (state.analysis?.colorWarning) console.warn(state.analysis.colorWarning)
  }, [state.analysis])

  // prefetch overlays de la región activa (tie)
  useEffect(() => {
    const s = ref.current
    if (s.phase !== 'choosing' || s.activeRegion == null || !s.analysis) return
    const region = s.analysis.regions.find(r => r.index === s.activeRegion)
    if (!region || region.decision !== 'tie') return
    const imageId = s.analysis.imageId
    region.candidates.forEach(c => {
      const choice = { family: c.family, wght: c.wght }
      const key = cacheKey(imageId, region.index, choice)
      if (s.overlayCache.has(key)) return
      api.overlay({ imageId, regionIndex: region.index, family: c.family, wght: c.wght })
        .then(r => dispatch({ type: 'OVERLAY_FETCHED', key, glyphs: r.glyphs, imageId }))
        .catch(() => { /* overlay fail es local: la candidata no previsualiza */ })
    })
  }, [state.phase, state.activeRegion, state.analysis])

  const upload = (file: File) => {
    if (ref.current.phase === 'analyzing') return
    const prev = ref.current.objectURL; if (prev) URL.revokeObjectURL(prev)
    dispatch({ type: 'UPLOAD', file, objectURL: URL.createObjectURL(file) })
  }
  const download = () => {
    const s = ref.current
    if (s.phase === 'composing' || !s.analysis) return
    dispatch({ type: 'COMPOSING' })
    const choices: Record<string, { family: string; wght: number }> = {}
    s.analysis.regions.forEach(r => { if (r.decision === 'tie' && s.choices[r.index]) choices[String(r.index)] = s.choices[r.index] })
    api.compose({ imageId: s.analysis.imageId, choices })
      .then(resp => dispatch({ type: 'COMPOSED', resp }))
      .catch(e => dispatch({ type: 'FAIL', status: e?.status ?? 0, message: e?.message ?? 'error', origin: 'compose' }))
  }
  return {
    state,
    upload, download,
    setActive: (i: number) => dispatch({ type: 'SET_ACTIVE', index: i }),
    arm: (c: { family: string; wght: number } | null) => dispatch({ type: 'ARM', choice: c }),
    choose: (i: number, c: { family: string; wght: number }) => dispatch({ type: 'CHOOSE', index: i, choice: c }),
    retry: () => dispatch({ type: 'RETRY' }),
    reset: () => dispatch({ type: 'RESET' }),
  }
}
```

- [ ] **Step 4: Write `ChooseScreen` tests (active-only + hold toggle), then implement it**

First write `web/src/components/ChooseScreen.test.tsx` (covers spec §6 "solo la región activa se pinta" + the "mantener" mechanism):
```tsx
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
```
Run `cd web && npx vitest run src/components/ChooseScreen.test.tsx` → FAIL (module unresolved). Then implement `web/src/components/ChooseScreen.tsx`:
```tsx
import { useState } from 'react'
import { Anchor } from './Anchor'
import { CandidateRail } from './CandidateRail'
import type { AppState } from '../state/useApp'
import { cacheKey } from '../state/useApp'
import type { Choice } from '../api/types'

export function ChooseScreen({ state, onArm, onChoose }: {
  state: AppState; onArm: (c: Choice | null) => void; onChoose: (i: number, c: Choice) => void
}) {
  const [held, setHeld] = useState(false)
  const a = state.analysis!
  const active = state.activeRegion != null ? a.regions.find(r => r.index === state.activeRegion) : null
  const overlayChoice = state.armed ?? (active && state.choices[active.index]) ?? null
  const glyphs = active && overlayChoice ? (state.overlayCache.get(cacheKey(a.imageId, active.index, overlayChoice)) ?? null) : null

  return (
    <>
      <div className="stage-head">
        <p className="eyebrow">Elección</p>
        <h1>{active ? '¿Cuál calza sobre tu logo?' : 'Listo para descargar'}</h1>
        {active && <p>La candidata se pinta en magenta encima del original. Pasa el cursor para previsualizar; haz clic para elegir.</p>}
      </div>
      {state.objectURL && <div className="anchor-wrap">
        <Anchor imageUrl={state.objectURL} width={a.width} height={a.height} glyphs={glyphs} showOverlay={!held} />
      </div>}
      <div className="rule" />
      {active && active.decision === 'tie' && (
        <>
          <button className={'toggle-hold ' + (held ? 'held' : '')}
                  onMouseDown={() => setHeld(true)} onMouseUp={() => setHeld(false)} onMouseLeave={() => setHeld(false)}>
            Mantener para ver original
          </button>
          <CandidateRail text={active.text} candidates={active.candidates}
                         chosen={state.choices[active.index] ?? null} armed={state.armed}
                         onArm={onArm} onChoose={c => onChoose(active.index, c)} />
        </>
      )}
    </>
  )
}
```

- [ ] **Step 5: Implement the full `App.tsx`**

Replace `web/src/App.tsx`:
```tsx
import { useApp, isComplete } from './state/useApp'
import { Rail } from './components/Rail'
import { Dropzone } from './components/Dropzone'
import { Analyzing } from './components/Analyzing'
import { EmptyState } from './components/EmptyState'
import { ChooseScreen } from './components/ChooseScreen'
import { ComposeScreen } from './components/ComposeScreen'

export default function App() {
  const app = useApp()
  const s = app.state
  const tieCount = s.analysis ? s.analysis.regions.filter(r => r.decision === 'tie').length : 0
  const doneCount = s.analysis ? s.analysis.regions.filter(r => r.decision === 'tie' && s.choices[r.index]).length : 0
  const complete = isComplete(s)
  const showRail = s.phase === 'choosing'

  let main = null
  if (s.phase === 'idle') main = <Dropzone onUpload={app.upload} />
  else if (s.phase === 'analyzing') main = <Analyzing file={s.file?.name ?? ''} />
  else if (s.phase === 'empty') main = <EmptyState onReset={app.reset} />
  else if (s.phase === 'choosing') main = <ChooseScreen state={s} onArm={app.arm} onChoose={app.choose} />
  else if (s.phase === 'composing') main = <Analyzing file="componiendo…" />
  else if (s.phase === 'done' && s.result) main = <ComposeScreen result={s.result} onBack={() => app.setActive(s.activeRegion ?? 0)} />
  else if (s.phase === 'error' && s.error) main = (
    <div className="panel"><div className="inner">
      <div className="ico">!</div>
      <h2>Algo falló</h2>
      <p>{s.error.message}</p>
      <div className="actions">
        {s.error.status === 404
          ? <button className="btn" onClick={app.reset}>Re-subir el logo</button>
          : <button className="btn" onClick={app.retry}>Reintentar</button>}
      </div>
    </div></div>
  )

  return (
    <div className="app">
      <div className="topbar">
        <span className="brand">recompose<span className="dot">.</span></span>
        {s.file && <span className="file">{s.file.name}</span>}
        <span className="spacer" style={{ flex: 1 }} />
        {/* La descarga vive SOLO al pie del riel (corte de Iris: "descarga al final del riel").
            Un único botón "Descargar SVG" evita el findByRole ambiguo en el test de integración. */}
      </div>
      <div className="body">
        {showRail && <Rail regions={s.analysis!.regions} active={s.activeRegion} choices={s.choices}
                           complete={complete} doneCount={doneCount} tieCount={tieCount}
                           onPick={app.setActive} onDownload={app.download} />}
        <div className="main">{main}</div>
      </div>
    </div>
  )
}
```

- [ ] **Step 6: Run the full suite + build**

Run: `cd web && npm test`
Expected: every suite PASSES (App integration: happy path, empty→EmptyState + colorWarning warn, analyze-fail→error).
Run: `cd web && npm run build`
Expected: type-checks and builds clean.

- [ ] **Step 7: Commit**

```bash
git add web/src/state/useApp.ts web/src/App.tsx web/src/App.test.tsx web/src/components/ChooseScreen.tsx web/src/components/ChooseScreen.test.tsx
git commit -m "feat(web): App + useApp (efectos) + ChooseScreen — wiring del happy path" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Manual Acceptance (after Task 8 — the judgment regression, owner = Samuel)

Run the backend (`python -m server`) and `cd web && npm run dev`, open `http://localhost:5173`:
1. **Logo de Ale** (`C:\Users\simon\Desktop\Ale\logo_ale.jpeg`) → 2 empates; resolve each by the magenta overlay; download → diff the SVG against `logo_ale_v01.svg` (must be byte-identical); re-judge the render in Blink.
2. **Logo de Maria** (`C:\Users\simon\Desktop\Maria\logo.png`) → EmptyState ("nada que recomponer") + a `console.warn` of the colorWarning; the app does NOT land on an empty choose screen.
3. **EXIF spike:** a real EXIF-rotated JPEG → the overlay stays pixel-aligned (validates `image-orientation:none` in Blink, which jsdom cannot).

---

## Self-Review

**Spec coverage:** §1 scope → Tasks 1–8 + manual acceptance. §2 structure → Task 1 (scaffold, styles), every component task. §3 Anchor invariant → Task 4 (+ Task 1 the no-max-height rule). §4 types/reducer/effects/client/compose → Tasks 2,3,8. Routing (empty/choosing/ready) → Task 3 + Task 8 integration. Gate general → Task 3 (`isComplete`). Discriminated union → Task 2. Cache imageId-keyed + stale drop → Task 3. §5 error model (origin, 404→reset, overlay-local) → Task 3 (RETRY) + Task 8 (effects catch overlay locally, App error screen). §6 tests → each task; contract trimmed → Task 2; manual acceptance (Ale/Maria/EXIF) → above. §7 assumptions honored (active-only, white bg, image-orientation) → Task 4. EmptyState → Task 6 + Task 8.

**Placeholder scan:** none — every step has full code/commands.

**Type consistency:** `Region` union, `Choice`, `AppState`, `Action`, `cacheKey`, `isComplete`, `reducer`, `useApp` used identically across Tasks 2/3/8. `Anchor` props (imageUrl/width/height/glyphs/showOverlay) consistent Task 4 ↔ ChooseScreen (Task 8). `Rail`/`CandidateRail`/`ComposeScreen`/`Dropzone`/`EmptyState` prop shapes consistent between their task and App (Task 8). `client.analyze/compose/overlay` + `ApiError` consistent Task 2 ↔ Task 8.
