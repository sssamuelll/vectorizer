export function EmptyState({ onReset }: { onReset: () => void }) {
  return (
    <div className="panel"><div className="inner">
      <div className="ico">∅</div>
      <h2>No encontramos texto para recomponer</h2>
      <p>Analizamos la imagen y no detectamos regiones de texto tipográfico. Recompose existe para reemplazar texto pixelado por su fuente real; sin texto, no hay nada que rehacer.</p>
      <div className="actions"><button className="btn" onClick={onReset}>Subir otro logo</button></div>
    </div></div>
  )
}
