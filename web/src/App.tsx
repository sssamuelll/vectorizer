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
