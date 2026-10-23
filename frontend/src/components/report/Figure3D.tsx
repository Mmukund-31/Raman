import { lazy, Suspense, type ReactNode } from 'react'
import type { Data, Layout } from 'plotly.js'

const Plot = lazy(() => import('./Plot3D'))

type Ticks = { vals: number[]; text: string[] }

const axis = (title: string, opts: { ticks?: Ticks; range?: [number, number]; wall?: boolean } = {}) => ({
  title: { text: title, font: { size: 11, color: '#334155' } },
  gridcolor: '#e6ebf1', zerolinecolor: '#cbd5e1', linecolor: '#94a3b8', showline: true,
  showbackground: opts.wall ?? true, backgroundcolor: '#f7faf8', showspikes: false, nticks: 6,
  tickfont: { size: 10, color: '#64748b' },
  ...(opts.ticks ? { tickvals: opts.ticks.vals, ticktext: opts.ticks.text, tickmode: 'array' } : {}),
  ...(opts.range ? { range: opts.range, autorange: false } : {}),
})

/**
 * Interactive 3D chart (drag to rotate, scroll to zoom) in the report's visual language: orthographic camera so spectra
 * keep their true proportions, a light floor and back wall, and optional labelled depth tracks (yTicks).
 */
export function Figure3D({ data, xTitle, yTitle, zTitle, height = 380, layout, label, aspect = { x: 2, y: 1, z: 0.8 }, camera, yTicks, xRange, zRange }: {
  data: Data[]; xTitle: string; yTitle: string; zTitle: string; height?: number; layout?: Partial<Layout>; label: string
  aspect?: { x: number; y: number; z: number }; camera?: { x: number; y: number; z: number }
  yTicks?: Ticks; xRange?: [number, number]; zRange?: [number, number]
}) {
  return (
    <figure aria-label={label} className="-mx-1">
      <Suspense fallback={<div style={{ height }} className="flex items-center justify-center text-xs text-slate-400">Loading 3D view…</div>}>
        <Plot
          data={data}
          layout={{
            height, margin: { t: 0, r: 0, l: 0, b: 0 }, paper_bgcolor: 'rgba(0,0,0,0)',
            font: { family: 'Inter, system-ui, sans-serif', size: 11, color: '#334155' },
            hoverlabel: { bgcolor: '#0f172a', bordercolor: '#0f172a', font: { color: '#fff', size: 12 } },
            showlegend: true, legend: { orientation: 'h', y: 1, x: 0, yanchor: 'bottom', font: { size: 11 }, bgcolor: 'rgba(0,0,0,0)' },
            scene: {
              xaxis: axis(xTitle, { range: xRange }), yaxis: axis(yTitle, { ticks: yTicks }), zaxis: axis(zTitle, { range: zRange, wall: false }),
              aspectmode: 'manual', aspectratio: aspect, dragmode: 'turntable',
              camera: { eye: camera ?? { x: 1.45, y: -1.6, z: 0.75 }, center: { x: 0, y: 0, z: -0.12 }, projection: { type: 'orthographic' } },
            },
            ...layout,
          } as Partial<Layout>}
          config={{ responsive: true, displaylogo: false }}
          style={{ width: '100%' }}
          useResizeHandler
        />
      </Suspense>
    </figure>
  )
}

/** A 2D and a 3D view of the same result, side by side on wide screens. */
export function FigurePair({ title, two, three, note }: { title?: ReactNode; two: ReactNode; three: ReactNode; note?: ReactNode }) {
  const tag = (t: string) => <span className="badge bg-accent-50 text-accent-700 ring-1 ring-accent-100">{t}</span>
  return (
    <div>
      {title}
      <div className="grid gap-4 xl:grid-cols-2">
        <div className="min-w-0 rounded-xl border border-slate-200 bg-white p-3"><div className="mb-1 flex justify-end">{tag('2D')}</div>{two}</div>
        <div className="min-w-0 rounded-xl border border-slate-200 bg-white p-3">
          <div className="mb-1 flex items-center justify-between gap-2"><span className="text-[11px] text-slate-400">Drag to rotate · scroll to zoom</span>{tag('3D')}</div>
          {three}
        </div>
      </div>
      {note && <div className="mt-2 text-sm text-slate-600">{note}</div>}
    </div>
  )
}
