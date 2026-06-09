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
