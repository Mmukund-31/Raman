import { useState, type ReactNode } from 'react'
import type { Data } from 'plotly.js'
import { SpectrumPlot } from '../SpectrumPlot'
import { Figure } from './Figure'
import { download, fetchFullReportHtml, printHtml, processedCsv } from '../../services/report'
import type { FullReport, VisualSummary } from '../../types/report'

// Validated pair (dataviz validator, white surface): sample = slot 1 blue, reference = slot 2 orange.
const SAMPLE = '#2a78d6'
const REFERENCE = '#eb6834'
const MUTED_BAR = '#c3c2b7'
const STATUS = { good: '#0ca30c', critical: '#d03b3b', warning: '#fab219' }

function H({ children }: { children: ReactNode }) {
  return <h2 className="mb-3 text-base font-semibold text-slate-900">{children}</h2>
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

/** The answer in one glance: icon + verdict + one sentence + a three-step "how sure" meter. */
function Answer({ r, v }: { r: FullReport; v: VisualSummary }) {
  const c = v.confidence
  const tone = c.level >= 2 ? { bg: 'bg-emerald-50', ring: 'ring-emerald-200', icon: '✓', color: STATUS.good, word: 'Match found' }
    : c.level === 1 ? { bg: 'bg-amber-50', ring: 'ring-amber-200', icon: 'i', color: STATUS.warning, word: 'Demo result' }
      : { bg: 'bg-slate-50', ring: 'ring-slate-200', icon: '?', color: '#52514e', word: 'No clear match' }
  const steps = ["Can't tell", 'Likely', 'Confident']
  const filled = c.level === 3 ? 3 : c.level === 2 ? 2 : c.level === 0 ? 1 : 0
  return (
    <section aria-label="Answer" className={`rounded-2xl ${tone.bg} p-6 ring-1 ${tone.ring} sm:p-8`}>
      <div className="flex items-start gap-5">
        <span aria-hidden className="flex h-14 w-14 flex-none items-center justify-center rounded-full text-2xl font-bold text-white" style={{ background: tone.color }}>{tone.icon}</span>
        <div className="min-w-0">
          <p className="text-sm font-semibold tracking-wide text-slate-600 uppercase">{tone.word}</p>
          <p className="mt-1 text-2xl font-semibold text-balance text-slate-900 sm:text-[28px] sm:leading-tight">{r.explanation?.headline ?? r.brief.headline}</p>
        </div>
      </div>
      <div className="mt-6">
        <p className="text-sm font-medium text-slate-700">How sure are we? <span className="font-semibold text-slate-900">{c.label}</span></p>
        {c.level === 1 ? (
          <p className="mt-2 text-sm text-slate-600">{c.reason}</p>
        ) : (
          <>
            <div role="meter" aria-label="Confidence" aria-valuemin={1} aria-valuemax={3} aria-valuenow={filled} aria-valuetext={c.label} className="mt-2 grid max-w-md grid-cols-3 gap-1">
              {steps.map((s, i) => (
                <div key={s}>
                  <div className={`h-2 rounded-full ${i < filled ? '' : 'bg-white ring-1 ring-slate-200'}`} style={i < filled ? { background: filled === 1 ? '#898781' : STATUS.good } : undefined} />
                  <p className={`mt-1 text-xs ${i === filled - 1 ? 'font-semibold text-slate-900' : 'text-slate-500'}`}>{s}</p>
                </div>
              ))}
            </div>
            <p className="mt-2 text-sm text-slate-600">{c.reason}</p>
          </>
        )}
      </div>
    </section>
  )
}

/** Figure 1: the sample drawn over the best-matching reference, both scaled to their own maximum. */
function Overlay({ v }: { v: VisualSummary }) {
  const o = v.overlay
  const traces: Data[] = [{
    x: o.x, y: o.sample, type: 'scatter', mode: 'lines', name: 'Your sample', line: { color: SAMPLE, width: 2 },
    hovertemplate: 'Your sample: %{y:.2f}<extra></extra>',
  }]
  if (o.reference) traces.push({
    x: o.reference.x, y: o.reference.y, type: 'scatter', mode: 'lines', name: `${o.reference_name} (reference)`,
    line: { color: REFERENCE, width: 2 }, opacity: 0.9, hovertemplate: `${o.reference_name}: %{y:.2f}<extra></extra>`,
  })
  const annotations = o.peaks.map((p, i) => ({
    x: p, y: o.peak_heights[i], text: `${p}`, showarrow: true, arrowhead: 0, arrowcolor: '#898781', ax: 0, ay: -22,
    font: { size: 11, color: '#52514e' },
  }))
  return (
    <section>
      <H>{!o.reference ? 'Your spectrum' : v.candidates.named ? `Your spectrum next to ${o.reference_name}` : `Your spectrum next to the closest material, ${o.reference_name}`}</H>
      <Figure data={traces} height={320} label="Sample spectrum overlaid on the best-matching reference spectrum"
        xTitle="Raman shift (cm⁻¹) — position of each peak" yTitle="Relative strength"
        layout={{ hovermode: 'x unified', legend: { orientation: 'h', y: 1.12, x: 0, font: { size: 12 } }, margin: { t: 36, r: 16, l: 56, b: 52 },
          yaxis: { gridcolor: '#eef2f7', zeroline: false, tickfont: { size: 11, color: '#64748b' }, title: { text: 'Relative strength', font: { size: 12 } }, range: [-0.05, 1.18] },
          annotations }} />
      <p className="text-sm text-slate-600">
        Each spike (“peak”) is part of the material’s fingerprint. {o.reference ? 'The more the blue and orange peaks line up, the better the match.' : ''}
        {o.peaks.length > 0 && <> Labelled numbers are {o.reference ? 'peaks both spectra share' : 'the strongest peaks'}.</>}
      </p>
    </section>
  )
}

/** Figure 2: closest materials as simple bars, with the level needed to name one. */
function Candidates({ v }: { v: VisualSummary }) {
  const { items, threshold, named } = v.candidates
  return (
    <section>
      <H>How close were the candidates?</H>
      <div className="relative">
        <ol className="space-y-3">
          {items.map(c => (
            <li key={c.name} title={`${c.name}: similarity ${c.score.toFixed(2)} out of 1${c.category === 'synthetic' ? ' (simulated reference)' : ''}`}>
              <div className="flex justify-between text-sm">
                <span className={c.top ? 'font-semibold text-slate-900' : 'text-slate-600'}>{c.name}{c.category === 'synthetic' && <span className="ml-1 text-xs text-slate-400">(demo)</span>}</span>
                <span className="text-slate-700 tabular-nums">{c.score.toFixed(2)}</span>
              </div>
              <div className="relative mt-1 h-2.5 rounded-full bg-slate-100">
                <div className="h-full rounded-full" style={{ width: `${Math.min(1, c.score) * 100}%`, background: c.top && named ? SAMPLE : MUTED_BAR }} />
                <div aria-hidden className="absolute -top-1 -bottom-1 w-px bg-slate-500" style={{ left: `${threshold * 100}%` }} />
              </div>
            </li>
          ))}
        </ol>
      </div>
      <p className="mt-3 text-xs text-slate-500">Bars show how alike each material’s fingerprint is, from 0 (nothing alike) to 1 (identical). The thin line at {threshold.toFixed(2)} is the minimum needed before we name a material; the gap to the next bar matters too.</p>
    </section>
  )
}

function Checks({ v }: { v: VisualSummary }) {
  return (
    <section>
      <H>Checks we ran</H>
      <ul className="space-y-2.5">
        {v.checks.map(c => (
          <li key={c.id} className="flex gap-3">
            <span aria-hidden className="mt-0.5 flex h-5 w-5 flex-none items-center justify-center rounded-full text-[11px] font-bold text-white" style={{ background: c.passed ? STATUS.good : STATUS.critical }}>{c.passed ? '✓' : '✕'}</span>
            <span className="text-sm">
              <span className="font-medium text-slate-900">{c.label}</span>
              <span className="sr-only">{c.passed ? ' — passed' : ' — not passed'}</span>
              <span className="block text-slate-500">{c.detail}</span>
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}

function Technical({ r }: { r: FullReport }) {
  const b = r.brief
  const e = r.explanation
  return (
    <details className="rounded-2xl border border-slate-200 bg-white">
      <summary className="cursor-pointer px-5 py-4 text-sm font-medium text-slate-700">Technical details <span className="font-normal text-slate-500">· for specialists</span></summary>
      <div className="space-y-8 border-t border-slate-200 px-5 py-6">
        <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-slate-200 bg-slate-200 lg:grid-cols-4">
          {b.metrics.map(m => (
            <div key={m.label} className="bg-white px-4 py-3">
              <dt className="text-xs text-slate-500">{m.label}</dt>
              <dd className="mt-1 text-lg font-semibold text-slate-900">{m.value}</dd>
              {m.note && <dd className="text-[11px] text-slate-400">{m.note}</dd>}
            </div>
          ))}
        </dl>
        <section>
          <h3 className="mb-2 text-sm font-semibold text-slate-900">Processed spectrum with all detected peaks</h3>
          <SpectrumPlot r={r.sections.spectrum.data} kind="processed" height={300} />
        </section>
        <div className="grid gap-8 lg:grid-cols-2">
          <section>
            <h3 className="mb-2 text-sm font-semibold text-slate-900">Principal peaks</h3>
            <table className="w-full text-sm">
              <thead><tr className="border-b border-slate-300 text-left text-xs text-slate-500"><th className="py-2 pr-3 font-medium">Position (cm⁻¹)</th><th className="py-2 pr-3 font-medium">Rel. intensity</th><th className="py-2 font-medium">Tentative region</th></tr></thead>
              <tbody>{b.peaks.map(p => (
                <tr key={p.position} className="border-b border-slate-100">
                  <td className="py-1.5 pr-3 tabular-nums">{p.position.toFixed(0)}</td>
                  <td className="py-1.5 pr-3 tabular-nums">{p.relative_height.toFixed(2)}</td>
                  <td className="py-1.5 text-slate-600">{p.assignment ?? '—'}</td>
                </tr>))}</tbody>
            </table>
          </section>
          <section>
            <h3 className="mb-2 text-sm font-semibold text-slate-900">Reliability notes</h3>
            <Bullets items={r.evaluation?.headline ? [...b.limitations, r.evaluation.headline] : b.limitations} />
          </section>
        </div>
        {e && (
          <section>
            <h3 className="mb-2 text-sm font-semibold text-slate-900">Evidence behind the summary</h3>
            <ol className="space-y-1 text-sm text-slate-600">{e.evidence.map(x => <li key={x.id}><span className="font-mono text-xs text-slate-400">{x.id}</span> <b className="font-medium text-slate-800">{x.label}.</b> {x.text}</li>)}</ol>
            <p className="mt-2 text-xs text-slate-500">{e.source === 'llm_verified' ? 'Summary written by AI from these facts and checked automatically.' : 'Summary written from fixed templates using these facts.'}</p>
          </section>
        )}
        <p className="text-xs leading-relaxed text-slate-500">
          <b className="text-slate-600">Methods.</b> {b.methods}
          {b.not_performed.length > 0 && <> <b className="text-slate-600">Not performed:</b> {b.not_performed.map(x => `${x.title} (${x.reason})`).join('; ')}.</>}
        </p>
      </div>
    </details>
  )
}

export function ResearchReport({ r, onNew }: { r: FullReport; onNew: () => void }) {
  const when = new Date(r.generated_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
  const v = r.visual
  const e = r.explanation
  const found = (e?.what_we_found.map(f => f.text) ?? r.brief.findings).slice(0, 3)
  const next = (e?.next_steps ?? r.brief.recommendations).slice(0, 3)
  return (
    <article aria-label="Analysis report" className="card fade-up mx-auto max-w-4xl overflow-hidden">
      <header className="flex flex-wrap items-end justify-between gap-6 border-b border-slate-200 px-6 py-5 sm:px-10">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-slate-900">Spectrum analysis report</h1>
          <p className="mt-1 text-sm text-slate-500"><span className="font-medium text-slate-700">{r.sample_id}</span> · {when}</p>
        </div>
        <Actions r={r} onNew={onNew} />
      </header>

      <div className="space-y-10 px-6 py-8 sm:px-10">
        {v && <Answer r={r} v={v} />}
        {v && <Overlay v={v} />}
        {v && (
          <div className="grid gap-10 md:grid-cols-2">
            <Candidates v={v} />
            <Checks v={v} />
          </div>
        )}
        <div className="grid gap-10 md:grid-cols-2">
          <section><H>What this means</H><Bullets items={found} /></section>
          <section><H>What to do next</H><Bullets items={next} /></section>
        </div>
        <Technical r={r} />
      </div>

      <footer className="border-t border-slate-200 bg-slate-50/70 px-6 py-4 text-xs leading-relaxed text-slate-500 sm:px-10">
        RamanReach {r.software_version} · Research use only, not for medical, legal or safety decisions. A similarity score is not a probability; only materials in the reference library can be recognised.
      </footer>
    </article>
  )
}
