import Plotly from 'plotly.js-basic-dist-min'
import type { Data, Layout } from 'plotly.js'
import createPlotlyComponent from 'react-plotly.js/factory'
import type { Common, DataClass, Insight, SelfCheck, Study } from '../types/research'

const Plot = createPlotlyComponent(Plotly)


const CLASS_TEXT: Record<string, { text: string; cls: string }> = {
  simulated: { text: 'SIMULATED — not a measurement', cls: 'border-violet-700 bg-violet-50 text-violet-900' },
  synthetic_example: { text: 'SYNTHETIC EXAMPLE — not a measurement', cls: 'border-violet-700 bg-violet-50 text-violet-900' },
  measured: { text: 'USER-DECLARED MEASURED DATA — origin and calibration not verified', cls: 'border-emerald-700 bg-emerald-50 text-emerald-900' },
}

export function DataBadge({ dc }: { dc: DataClass }) {
  const c = CLASS_TEXT[dc] ?? { text: dc, cls: 'border-slate-500 bg-slate-50' }
  return <span className={`inline-block rounded border px-2 py-0.5 text-xs font-semibold ${c.cls}`}>{c.text}</span>
}

export function Chart({ traces, title, xTitle, yTitle, dc, condition, height = 320, layout }: {
  traces: Data[]; title: string; xTitle: string; yTitle: string; dc: DataClass; condition: string; height?: number; layout?: Partial<Layout>
}) {
  return (
    <figure className="rounded bg-white p-2">
      <Plot
        data={traces}
        layout={{
          title: { text: title }, xaxis: { title: { text: xTitle } }, yaxis: { title: { text: yTitle } },
          margin: { t: 40, r: 10, l: 60, b: 50 }, legend: { orientation: 'h', y: -0.25 }, height, ...layout,
        }}
        config={{ responsive: true, displaylogo: false }} style={{ width: '100%' }} useResizeHandler
      />
      <figcaption className="flex flex-wrap items-center gap-2 text-xs text-slate-600">
        <DataBadge dc={dc} /> <span>Condition: {condition}</span> <span>Reference library: synthetic</span>
      </figcaption>
    </figure>
  )
}

const LEVEL: Record<string, { label: string; cls: string }> = {
  observed: { label: 'Observed result', cls: 'bg-sky-100 text-sky-900' },
  supported: { label: 'Supported interpretation', cls: 'bg-emerald-100 text-emerald-900' },
  hypothesis: { label: 'Hypothesis — needs further testing', cls: 'bg-amber-100 text-amber-900' },
  inconclusive: { label: 'Inconclusive', cls: 'bg-slate-200 text-slate-800' },
}

export function Insights({ items }: { items: Insight[] }) {
  return (
    <section className="rounded bg-white p-4 shadow-sm" aria-label="Insights">
      <h3 className="font-semibold">What the numbers support</h3>
      <p className="mb-2 text-xs text-slate-600">Each statement is generated from a computed metric. Model confidence is never used as evidence.</p>
      <ul className="space-y-2 text-sm">
        {items.map(i => (
          <li key={i.id} className="rounded border border-slate-200 p-2">
            <span className={`mr-2 rounded px-1.5 py-0.5 text-xs font-semibold ${LEVEL[i.level]?.cls}`}>{LEVEL[i.level]?.label}</span>
            {i.statement}
            <details className="mt-1 text-xs text-slate-600">
              <summary className="cursor-pointer">Evidence, validation and limits</summary>
              <ul className="list-disc pl-5">
                {i.evidence.map((e, k) => (
                  <li key={k}>{e.metric}: <b>{String(e.value ?? 'n/a')}</b> {e.unit}{e.baseline != null && <> (baseline {String(e.baseline)})</>}</li>
                ))}
                <li>Data: {i.data_class} · Validation: {i.validation_status}</li>
                {i.limitations.map((l, k) => <li key={`l${k}`}>Limit: {l}</li>)}
              </ul>
            </details>
          </li>
        ))}
      </ul>
    </section>
  )
}

export function Checks({ items }: { items?: SelfCheck[] }) {
  if (!items?.length) return null
  return (
    <section className="rounded bg-white p-4 text-sm shadow-sm" aria-label="Self-checks">
      <h3 className="font-semibold">Self-checks against known ground truth</h3>
      <ul className="list-disc pl-5">
        {items.map(c => <li key={c.name}><b>{c.passed === null ? 'n/a' : c.passed ? 'PASS' : 'FAIL'}</b> — {c.name}{c.value != null && ` (value ${Number(c.value).toFixed(3)})`}</li>)}
      </ul>
    </section>
  )
}

export function Notes({ items, title = 'Warnings and limitations' }: { items: string[]; title?: string }) {
  if (!items.length) return null
  return (
    <div role="note" className="rounded border border-amber-600 bg-amber-50 p-3 text-sm">
      <b>{title}</b>
      <ul className="list-disc pl-5">{items.map((w, i) => <li key={i}>{w}</li>)}</ul>
    </div>
  )
}

export function AddToReport({ study, onAdd }: { study: Study; onAdd: (s: Study) => void }) {
  return <button onClick={() => onAdd(study)} className="rounded border border-blue-700 px-3 py-1 text-sm text-blue-800 hover:bg-blue-50">Add to report</button>
}

export function Plain({ r }: { r: Common }) {
  return (
    <section className="rounded border border-slate-300 bg-white p-4 text-sm shadow-sm" aria-label="Plain-language summary">
      <h3 className="font-semibold">In plain language</h3>
      <p className="mt-1"><b>What changed:</b> {r.report.changed}</p>
      <p className="mt-1"><b>Can we trust it?</b> {r.report.trust}</p>
      <p className="mt-1"><b>Conclusion:</b> {r.report.conclusion}</p>
    </section>
  )
}

export function Busy({ busy, error }: { busy: boolean; error: string }) {
  return (
    <>
      {busy && <p role="status" className="text-sm text-slate-600">Running… this can take a few seconds.</p>}
      {error && <p role="alert" className="mt-2 rounded border border-red-600 bg-red-50 p-2 text-sm text-red-800">Error: {error}</p>}
    </>
  )
}
