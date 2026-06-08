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

test('BACK desde done vuelve a choosing preservando el resultado', () => {
  let s = reducer(afterUpload(), { type: 'ANALYZED', resp: resp([tie(0)]), seq: 1 })
  s = reducer(s, { type: 'CHOOSE', index: 0, choice: { family: 'A', wght: 400 } })
  s = reducer(s, { type: 'COMPOSED', resp: { svg: '<svg/>', provenance: [], ignoradas: [] } })
  expect(s.phase).toBe('done')
  const back = reducer(s, { type: 'BACK' })
  expect(back.phase).toBe('choosing')
  expect(back.result).not.toBeNull()              // el resultado se preserva
  expect(back.choices[0]).toEqual({ family: 'A', wght: 400 })  // la elección se preserva
})
