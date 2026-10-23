import { useState, type ReactNode } from 'react'
import { SpectrumPlot } from '../SpectrumPlot'
import { download, fetchFullReportHtml, printHtml, processedCsv } from '../../services/report'
import type { FullReport } from '../../types/report'

function H({ children }: { children: ReactNode }) {
  return <h2 className="mb-3 text-[11px] font-semibold tracking-[0.14em] text-accent-700 uppercase">{children}</h2>
}

function Bullets({ items }: { items: string[] }) {
  return (
    <ul className="space-y-2">
      {items.map((t, i) => <li key={i} className="flex gap-3 leading-relaxed text-slate-700"><span aria-hidden className="mt-2.5 h-1 w-1 flex-none rounded-full bg-slate-400" />{t}</li>)}
    </ul>
  )
}

function Actions({ r, onNew }: { r: FullReport; onNew: () => void }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const pdf = async () => {
    setBusy(true); setErr('')
    try { printHtml(await fetchFullReportHtml(r)) } catch (e) { setErr(`Could not prepare the PDF: ${(e as Error).message}`) }
    setBusy(false)
  }
  return (
    <div className="no-print flex flex-col items-end gap-1">
      <div className="flex flex-wrap justify-end gap-2">
        <button className="btn-primary" onClick={pdf} disabled={busy} title="Opens the print dialog; choose “Save as PDF”.">{busy ? 'Preparing…' : 'Download PDF'}</button>
        <button className="btn-ghost" onClick={() => download(`${r.sample_id}-processed.csv`, processedCsv(r), 'text/csv')}>Export data</button>
        <button className="btn-ghost" onClick={onNew}>New analysis</button>
      </div>
      {err && <p role="alert" className="text-sm text-rose-700">{err}</p>}
    </div>
  )
}

export function ResearchReport({ r, onNew }: { r: FullReport; onNew: () => void }) {
  const b = r.brief
  const inc = !b.match_claimed
  const when = new Date(r.generated_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
  const max = Math.max(...b.references.map(x => x.score), 0.0001)
  return (
    <article aria-label="Research report" className="card fade-up overflow-hidden">
      <header className="flex flex-wrap items-end justify-between gap-6 border-b border-slate-200 px-6 py-6 sm:px-10">
        <div>
          <p className="text-[11px] font-semibold tracking-[0.14em] text-slate-500 uppercase">Research report · {b.report_id}</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-slate-900 sm:text-[28px]">Raman Spectral Analysis</h1>
          <p className="mt-1 text-sm text-slate-500">Sample <span className="font-medium text-slate-700">{r.sample_id}</span> · {when}</p>
        </div>
        <Actions r={r} onNew={onNew} />
      </header>

      <div className="space-y-10 px-6 py-8 sm:px-10">
        <section role="status" className={`border-l-4 py-1 pl-5 ${inc ? 'border-amber-500' : 'border-accent-600'}`}>
          <p className={`text-xs font-semibold tracking-wider uppercase ${inc ? 'text-amber-700' : 'text-accent-700'}`}>{b.verdict}</p>
          <p className="mt-1 text-lg font-medium text-slate-900 sm:text-xl">{b.headline}</p>
        </section>

        <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-slate-200 bg-slate-200 lg:grid-cols-4">
          {b.metrics.map(m => (
            <div key={m.label} className="bg-white px-5 py-4">
              <dt className="text-xs text-slate-500">{m.label}</dt>
              <dd className="mt-1 text-2xl font-semibold tracking-tight text-slate-900 tabular-nums">{m.value}</dd>
              {m.note && <dd className="text-[11px] text-slate-400">{m.note}</dd>}
            </div>
          ))}
        </dl>

        <div className="grid gap-10 md:grid-cols-2">
          <section><H>Summary of findings</H><Bullets items={b.findings} /></section>
          <section><H>Reliability</H><Bullets items={b.limitations} /></section>
        </div>

        <section>
          <H>Figure 1 · Processed spectrum</H>
          <SpectrumPlot r={r.sections.spectrum.data} kind="processed" height={340} />
          <p className="text-xs text-slate-500">Baseline-corrected and normalised. Markers show detected peaks, labelled in cm⁻¹. Drag to zoom, double-click to reset.</p>
        </section>

        <div className="grid gap-10 lg:grid-cols-5">
          <section className="lg:col-span-3">
            <H>Table 1 · Principal peaks</H>
            <table className="w-full text-sm">
              <thead><tr className="border-b border-slate-300 text-left text-xs text-slate-500"><th className="py-2 pr-3 font-medium">Position (cm⁻¹)</th><th className="py-2 pr-3 font-medium">Rel. intensity</th><th className="py-2 font-medium">Tentative region</th></tr></thead>
              <tbody>{b.peaks.map(p => (
                <tr key={p.position} className="border-b border-slate-100">
                  <td className="py-2 pr-3 font-medium tabular-nums">{p.position.toFixed(0)}</td>
                  <td className="py-2 pr-3 tabular-nums">{p.relative_height.toFixed(2)}</td>
                  <td className="py-2 text-slate-600">{p.assignment ?? '—'}</td>
                </tr>))}</tbody>
            </table>
            <p className="mt-2 text-xs text-slate-500">Regions are tentative textbook ranges, not assignments.</p>
          </section>
          <section className="lg:col-span-2">
            <H>Table 2 · Reference comparison</H>
            <ol className="space-y-3">{b.references.map((m, i) => (
              <li key={m.name}>
                <div className="flex justify-between text-sm"><span className={i === 0 && !inc ? 'font-medium text-slate-900' : 'text-slate-600'}>{m.name}</span><span className="tabular-nums text-slate-700">{m.score.toFixed(3)}</span></div>
                <div aria-hidden className="mt-1 h-1 rounded-full bg-slate-100"><div className={`h-full rounded-full ${i === 0 && !inc ? 'bg-accent-600' : 'bg-slate-300'}`} style={{ width: `${Math.max(0, m.score / max) * 100}%` }} /></div>
              </li>))}
            </ol>
            <p className="mt-3 text-xs text-slate-500">Cosine similarity of band shape. Not a probability of identity.</p>
          </section>
        </div>

        <section>
          <H>Conclusion and recommendations</H>
          <p className="mb-4 leading-relaxed text-slate-800">
            {b.headline} {inc ? 'The evidence does not meet the criteria for a match claim.' : 'This is a provisional similarity result, not a validated identification.'}
          </p>
          <Bullets items={b.recommendations} />
        </section>
      </div>

      <footer className="border-t border-slate-200 bg-slate-50/70 px-6 py-5 text-xs leading-relaxed text-slate-500 sm:px-10">
        <b className="text-slate-600">Methods.</b> {b.methods}
        {b.not_performed.length > 0 && <> <b className="text-slate-600">Not performed:</b> {b.not_performed.map(x => `${x.title} (${x.reason})`).join('; ')}.</>}
        {' '}RamanReach {r.software_version}. Research use only; not for diagnostic or safety decisions.
      </footer>
    </article>
  )
}
