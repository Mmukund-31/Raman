import type { Data } from 'plotly.js'

/** Thin a series to about n points so WebGL surfaces stay light. */
export function thin<T>(a: T[], n = 400): T[] {
  const step = Math.max(1, Math.ceil(a.length / n))
  return a.filter((_, i) => i % step === 0)
}

/** Hex colour mixed toward white by t (0 = colour, 1 = white); surfaces ignore alpha inside colour scales. */
export function tint(hex: string, t: number) {
  const v = parseInt(hex.slice(1), 16)
  const mix = (c: number) => Math.round(c + (255 - c) * t)
  return `rgb(${mix((v >> 16) & 255)},${mix((v >> 8) & 255)},${mix(v & 255)})`
}

/** Keep only labels at least `gap` apart (strongest first), so stacked peaks do not print on top of each other. */
export function spaced(xs: number[], heights: number[], gap = 70): boolean[] {
  const keep = xs.map(() => false)
  const order = xs.map((_, i) => i).sort((a, b) => heights[b] - heights[a])
  for (const i of order) if (!order.some(j => keep[j] && Math.abs(xs[j] - xs[i]) < gap)) keep[i] = true
  return keep
}

/**
 * A waterfall "curtain": the spectrum drawn as a filled profile standing on the floor at a fixed depth, with a crisp
 * line along its top edge. The edge line carries the legend entry and the hover; the fill is decorative.
 */
export function curtain(x: number[], z: number[], depth: number, color: string, name: string,
  opts: { legendgroup?: string; showlegend?: boolean; floor?: number; hover?: string; fill?: number } = {}): Data[] {
  const xs = thin(x), zs = thin(z)
  const floor = opts.floor ?? 0
  const group = opts.legendgroup ?? name
  return [
    {
      type: 'surface', x: [xs, xs], y: [xs.map(() => depth), xs.map(() => depth)], z: [xs.map(() => floor), zs],
      surfacecolor: [xs.map(() => 0), xs.map(() => 1)], colorscale: [[0, tint(color, 0.92)], [1, tint(color, 0.35)]],
      cmin: 0, cmax: 1, showscale: false, opacity: opts.fill ?? 0.75, hoverinfo: 'skip', legendgroup: group, showlegend: false,
      lighting: { ambient: 1, diffuse: 0, specular: 0, roughness: 1, fresnel: 0 }, contours: { x: { highlight: false }, y: { highlight: false }, z: { highlight: false } },
    } as unknown as Data,
    {
      type: 'scatter3d', mode: 'lines', name, x: xs, y: xs.map(() => depth), z: zs, line: { color, width: 3.5 },
      legendgroup: group, showlegend: opts.showlegend ?? true,
      hovertemplate: opts.hover ?? `${name}<br>%{x:.0f} cm⁻¹ · %{z:.3f}<extra></extra>`,
    } as Data,
  ]
}
