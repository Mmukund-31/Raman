import Plotly from 'plotly.js-basic-dist-min'
import type { Data } from 'plotly.js'
import createPlotlyComponent from 'react-plotly.js/factory'
import type { Result } from '../types'

const Plot = createPlotlyComponent(Plotly)

export function SpectrumPlot({ r, kind }: { r: Result; kind: 'raw' | 'processed' }) {
  const raw = kind === 'raw'
  const traces: Data[] = [
    { x: r.x, y: raw ? r.raw : r.processed, type: 'scatter', mode: 'lines', name: raw ? 'Raw' : 'Processed', line: { color: '#1d4ed8', width: 1.5 } },
  ]
  if (raw) traces.push({ x: r.x, y: r.baseline, type: 'scatter', mode: 'lines', name: 'Estimated baseline', line: { color: '#b45309', dash: 'dash', width: 1.5 } })
  else traces.push({
    x: r.peaks.map(p => p.position), y: r.peaks.map(p => p.height), type: 'scatter', mode: 'markers', name: 'Peaks',
    marker: { color: '#be123c', size: 8, symbol: 'diamond' },
  })
  return (
    <Plot
      data={traces}
      layout={{
        title: { text: raw ? 'Raw spectrum' : 'Processed spectrum' },
        xaxis: { title: { text: 'Raman shift (cm⁻¹)' } },
        yaxis: { title: { text: raw ? 'Intensity (counts)' : 'Normalized intensity (a.u.)' } },
        margin: { t: 40, r: 10, l: 60, b: 50 }, legend: { orientation: 'h', y: -0.25 }, height: 320,
      }}
      config={{ responsive: true, displaylogo: false }}
      style={{ width: '100%' }}
      useResizeHandler
    />
  )
}
