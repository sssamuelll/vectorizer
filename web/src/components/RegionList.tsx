import type { Choice, Region } from '../api/types'

const BADGE: Record<Region['decision'], [string, string]> = {
  tie: ['tie', 'empate'], leader: ['leader', 'líder'],
  vectorized: ['vector', 'vectorizado'], no_font: ['nofont', 'sin fuente'],
}

export function RegionList({ regions, active, choices, onPick }: {
  regions: Region[]; active: number | null; choices: Record<number, Choice>; onPick: (i: number) => void
}) {
  return (
    <>
      <p className="lbl">Regiones detectadas</p>
      <div className="regions">
        {regions.map(r => {
          const chosen = choices[r.index]
          const [cls, txt] = chosen ? ['done', 'elegida'] : BADGE[r.decision]
          const meta = chosen ? chosen.family
            : r.decision === 'tie' ? `${r.candidates.length} candidatas`
            : r.decision === 'vectorized' ? 'se dibuja tal cual'
            : r.decision === 'leader' ? r.chosen.family : 'sin candidatas'
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
    </>
  )
}
