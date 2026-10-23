import Plotly from 'plotly.js-basic-dist-min'
import type { Data, Layout } from 'plotly.js'
import createPlotlyComponent from 'react-plotly.js/factory'

const Plot = createPlotlyComponent(Plotly)

const axis = { gridcolor: '#eef2f7', zerolinecolor: '#e2e8f0', linecolor: '#cbd5e1', tickfont: { size: 11, color: '#64748b' }, automargin: true }

/** Interactive Plotly chart with the report's shared visual language. */
export function Figure({ data, xTitle, yTitle, height = 340, layout, label }: {
  data: Data[]; xTitle: string; yTitle: string; height?: number; layout?: Partial<Layout>; label: string
}) {
  return (
    <figure aria-label={label} className="-mx-2">
      <Plot
        data={data}
        layout={{
          height, margin: { t: 16, r: 16, l: 64, b: 56 }, paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
          font: { family: 'Inter, system-ui, sans-serif', size: 12, color: '#334155' }, hovermode: 'closest',
          hoverlabel: { bgcolor: '#0f172a', bordercolor: '#0f172a', font: { color: '#fff', size: 12 } },
          ...layout,
          // axis overrides are merged into the shared axis style rather than replacing it
          xaxis: { ...axis, zeroline: false, title: { text: xTitle, font: { size: 12 } }, ...layout?.xaxis }, yaxis: { ...axis, title: { text: yTitle, font: { size: 12 } }, ...layout?.yaxis },
          legend: { orientation: 'h', y: -0.22, font: { size: 11 }, ...layout?.legend },
        }}
        config={{ responsive: true, displaylogo: false, modeBarButtonsToRemove: ['lasso2d', 'select2d'] }}
        style={{ width: '100%' }}
        useResizeHandler
      />
    </figure>
  )
}
