import { useApp, isComplete } from './state/useApp'
import { FlowTracker } from './components/FlowTracker'
import { RegionList } from './components/RegionList'
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
  const choosing = s.phase === 'choosing'

  let main = null
  if (s.phase === 'idle') main = <Dropzone onUpload={app.upload} />
  else if (s.phase === 'analyzing') main = <Analyzing file={s.file?.name ?? ''} />
  else if (s.phase === 'empty') main = <EmptyState onReset={app.reset} />
  else if (s.phase === 'choosing') main = <ChooseScreen state={s} onArm={app.arm} onChoose={app.choose} />
  else if (s.phase === 'composing') main = <Analyzing file="componiendo…" />
  else if (s.phase === 'done' && s.result) main = <ComposeScreen result={s.result} onBack={app.back} />
  else if (s.phase === 'error' && s.error) main = (
    <div className="panel"><div className="inner">
      <div className="ico" style={{ background: 'var(--bad-soft)', color: 'var(--bad)' }}>!</div>
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
        <span className="spacer" />
        {choosing && <span className="counter"><b>{doneCount}</b> de <b>{tieCount}</b> elegidas</span>}
      </div>
      <div className="body">
        <aside className="rail">
          <FlowTracker phase={s.phase} />
          {choosing && s.analysis && (
            <RegionList regions={s.analysis.regions} active={s.activeRegion} choices={s.choices} onPick={app.setActive} />
          )}
          <div className="foot">
            {choosing ? (
              <>
                <p className="note">
                  {complete
                    ? 'Todas las regiones tienen fuente. Ya puedes descargar el SVG.'
                    : 'Elige una fuente por cada región en empate. La descarga se habilita al completarlas.'}
                </p>
                <button className="btn block" disabled={!complete} onClick={app.download}>Descargar SVG</button>
              </>
            ) : (
              <p className="note">Una imagen a la vez. El original vive en tu navegador, nunca vuelve del servidor.</p>
            )}
          </div>
        </aside>
        <div className="main">{main}</div>
      </div>
    </div>
  )
}
