import type { Data } from 'plotly.js'
import { Figure } from './report/Figure'
import { COLORS } from './theme'
import type { Peak } from '../types'

export interface SpectrumSeries { x: number[]; raw: number[]; baseline: number[]; processed: number[]; peaks: Peak[] }

export function SpectrumPlot({ r, kind, height = 360 }: { r: SpectrumSeries; kind: 'raw' | 'processed'; height?: number }) {
  const raw = kind === 'raw'
  const traces: Data[] = [{
    x: r.x, y: raw ? r.raw : r.processed, type: 'scatter', mode: 'lines', name: raw ? 'Raw spectrum' : 'Processed spectrum',
    line: { color: COLORS.accent, width: 1.6 }, hovertemplate: '%{x:.1f} cm⁻¹<br>%{y:.4g}<extra></extra>',
  }]
  if (raw) traces.push({ x: r.x, y: r.baseline, type: 'scatter', mode: 'lines', name: 'Estimated baseline (subtracted)', line: { color: COLORS.baseline, dash: 'dash', width: 1.4 }, hoverinfo: 'skip' })
  else traces.push({
    x: r.peaks.map(p => p.position), y: r.peaks.map(p => p.height), type: 'scatter', mode: 'text+markers', name: 'Detected peaks (label = position, cm⁻¹)',
    text: r.peaks.map(p => p.position.toFixed(0)), textposition: 'top center', textfont: { size: 10, color: COLORS.peak },
    marker: { color: COLORS.peak, size: 7, symbol: 'diamond' },
    hovertemplate: 'Peak at %{x:.1f} cm⁻¹<br>height %{y:.4g}<extra></extra>',
  })
  return (
    <Figure data={traces} height={height} label={raw ? 'Raw spectrum with estimated baseline' : 'Processed spectrum with detected peaks'}
      xTitle="Raman shift (cm⁻¹)" yTitle={raw ? 'Intensity (as supplied: counts or a.u.)' : 'Processed intensity (a.u., normalised)'} />
  )
}
