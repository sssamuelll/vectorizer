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
