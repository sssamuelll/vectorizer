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
