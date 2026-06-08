import { useEffect, useReducer, useRef } from 'react'
import * as api from '../api/client'
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
