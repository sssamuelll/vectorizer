export function Analyzing({ file }: { file: string }) {
  return (
    <div className="analyzing"><div className="inner">
      <p className="eyebrow">Analizando</p>
      <h1 style={{ fontSize: 20, fontWeight: 600, margin: 0 }}>Leyendo {file}</h1>
      <div className="scan-bar"><i /></div>
    </div></div>
  )
}
