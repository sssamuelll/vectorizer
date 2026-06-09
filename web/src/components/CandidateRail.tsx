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
