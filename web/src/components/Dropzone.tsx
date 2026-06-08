import { useRef } from 'react'

export function Dropzone({ onUpload }: { onUpload: (f: File) => void }) {
  const ref = useRef<HTMLInputElement>(null)
  const pick = (files: FileList | null) => { if (files && files[0]) onUpload(files[0]) }
  return (
    <div className="dropzone" onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); pick(e.dataTransfer.files) }}>
      <p className="big">Suelta el logo aquí</p>
      <p className="sub">Una imagen de un logo de una sola tinta. La vectorizamos, encontramos el texto y lo rehacemos con la fuente real.</p>
      <input ref={ref} type="file" accept="image/*" style={{ display: 'none' }} onChange={e => pick(e.target.files)} />
      <button className="btn" onClick={() => ref.current?.click()}>Elegir imagen…</button>
    </div>
  )
}
