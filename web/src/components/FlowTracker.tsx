import type { Phase } from '../state/useApp'

const STEPS = [
  { k: 'subir', label: 'Subir' },
  { k: 'analizar', label: 'Analizar' },
  { k: 'elegir', label: 'Elegir' },
  { k: 'componer', label: 'Componer' },
] as const

// fase → índice del paso activo en el riel (subir/analizar/elegir/componer)
const ACTIVE: Record<Phase, number> = {
  idle: 0, analyzing: 1, choosing: 2, empty: 1, composing: 3, done: 3, error: 1,
}

export function FlowTracker({ phase }: { phase: Phase }) {
  const activeI = ACTIVE[phase]
  return (
    <div style={{ padding: '0 22px 18px' }}>
      <p className="lbl" style={{ padding: 0 }}>Flujo</p>
      <ol style={{ listStyle: 'none', margin: 0, padding: 0 }}>
        {STEPS.map((s, i) => (
          <li key={s.k} style={{
            display: 'flex', alignItems: 'baseline', gap: 10, padding: '5px 0',
            fontSize: 12.5, fontFamily: 'var(--mono)',
            color: i === activeI ? 'var(--ink)' : i < activeI ? 'var(--ink-2)' : 'var(--ink-3)',
          }}>
            <span style={{ width: 14, color: i < activeI ? 'var(--ok)' : i === activeI ? 'var(--magenta)' : 'var(--ink-3)' }}>
              {i < activeI ? '✓' : i === activeI ? '›' : '·'}
            </span>
            {s.label}
          </li>
        ))}
      </ol>
    </div>
  )
}
