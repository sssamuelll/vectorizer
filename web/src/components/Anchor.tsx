import type { GlyphPath } from '../api/types'

export function Anchor({ imageUrl, width, height, glyphs, showOverlay }: {
  imageUrl: string; width: number; height: number; glyphs: GlyphPath[] | null; showOverlay: boolean
}) {
  return (
    <div className="anchor-box" style={{ position: 'relative', display: 'inline-block',
                                         background: '#fff', maxWidth: '100%' }}>
      <img className="anchor-img" src={imageUrl} alt="logo original"
           style={{ display: 'block', width: '100%', height: 'auto', imageOrientation: 'none' as never }} />
      <svg className="overlay-layer" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="xMidYMid meet"
           style={{ position: 'absolute', inset: 0, width: '100%', height: '100%',
                    visibility: showOverlay ? 'visible' : 'hidden', pointerEvents: 'none' }}
           aria-hidden={!showOverlay}>
        {glyphs && <g fill="var(--magenta)">{glyphs.map((g, i) => <path key={i} d={g.d} transform={g.transform} />)}</g>}
      </svg>
    </div>
  )
}
