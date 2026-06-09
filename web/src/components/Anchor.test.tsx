import { render } from '@testing-library/react'
import { Anchor } from './Anchor'

const glyphs = [{ d: 'M0 0Z', transform: 'matrix(1 0 0 1 0 0)' },
                { d: 'M1 1Z', transform: 'matrix(1 0 0 1 5 0)' }]

test('el SVG usa viewBox natural + preserveAspectRatio meet y pinta los glifos en magenta', () => {
  const { container } = render(
    <Anchor imageUrl="blob:1" width={300} height={120} glyphs={glyphs} showOverlay />)
  const svg = container.querySelector('svg.overlay-layer')!
  expect(svg.getAttribute('viewBox')).toBe('0 0 300 120')
  expect(svg.getAttribute('preserveAspectRatio')).toBe('xMidYMid meet')
  const g = svg.querySelector('g')!
  expect(g.getAttribute('fill')).toBe('var(--magenta)')
  const paths = svg.querySelectorAll('path')
  expect(paths).toHaveLength(2)
  expect(paths[1].getAttribute('transform')).toBe('matrix(1 0 0 1 5 0)')
})

test('la <img> lleva image-orientation:none', () => {
  const { container } = render(<Anchor imageUrl="blob:1" width={10} height={10} glyphs={null} showOverlay />)
  const img = container.querySelector('img.anchor-img') as HTMLImageElement
  expect(img.style.imageOrientation).toBe('none')   // lee del CSSStyleDeclaration vivo (robusto vs serialización)
})

test('showOverlay=false oculta la capa', () => {
  const { container } = render(
    <Anchor imageUrl="blob:1" width={10} height={10} glyphs={glyphs} showOverlay={false} />)
  const svg = container.querySelector('svg.overlay-layer') as SVGElement
  expect(svg.style.visibility).toBe('hidden')
})
