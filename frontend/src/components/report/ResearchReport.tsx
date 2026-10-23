import { useState, type ReactNode } from 'react'
import type { Data } from 'plotly.js'
import { SpectrumPlot } from '../SpectrumPlot'
import { Figure } from './Figure'
import { Figure3D, FigurePair } from './Figure3D'
import { curtain, spaced } from './ribbons'
import { download, fetchFullReportHtml, printHtml, processedCsv } from '../../services/report'
import type { FullReport, VisualSummary } from '../../types/report'

// Validated pair (dataviz validator, white surface): sample = slot 1 blue, reference = slot 2 orange.
const SAMPLE = '#2a78d6'
const REFERENCE = '#eb6834'
const STATUS = { good: '#0ca30c', critical: '#d03b3b' }
const RESULT: Record<number, { word: string; color: string }> = {
  3: { word: 'Confirmed match', color: '#157f54' }, 2: { word: 'Probable match', color: '#157f54' },
  1: { word: 'Closest reference match', color: '#0f766e' }, 0: { word: 'No confident match', color: '#475569' },
}

function H({ n, children }: { n: string; children: ReactNode }) {
  return (
    <h2 className="mb-4 flex items-baseline gap-2 border-b border-accent-100 pb-2 text-lg font-semibold text-accent-900" style={{ fontFamily: 'var(--font-serif)' }}>
      <span aria-hidden className="text-accent-600 tabular-nums">{n}</span>{children}
    </h2>
  )
}

function Caption({ n, children }: { n: string; children: ReactNode }) {
  return <p className="mt-2 text-[13px] leading-relaxed text-slate-600"><b className="font-semibold text-slate-900">Figure {n}.</b> {children}</p>
}

function Bullets({ items }: { items: string[] }) {
  return (
    <ul className="space-y-2">
      {items.map((t, i) => <li key={i} className="flex gap-3 text-sm leading-relaxed text-slate-700"><span aria-hidden className="mt-2 h-1.5 w-1.5 flex-none rounded-full bg-accent-500" />{t}</li>)}
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

function library(r: FullReport) {
  const p = r.data_provenance
  const names: Record<string, string> = { measured: 'measured (RRUFF/ROD)', synthetic: 'literature-band' }
  const parts = Object.entries(p.references_by_category ?? {}).map(([c, n]) => `${n} ${names[c] ?? c}`).join(', ')
  return `${p.n_materials ?? '—'} materials, ${p.n_reference_spectra ?? '—'} spectra${parts ? ` (${parts})` : ''}`
}

/** 1 · Sample information, as a two-column specification list. */
function SampleInfo({ r }: { r: FullReport }) {
  const v = r.sections.validation.data
  const params = r.sections.spectrum.data.parameters ?? {}
  const exc = (r.inputs.metadata.excitation_nm as number | undefined) ?? r.sections.conditions.data?.excitation?.excitation_nm
  const rows: [string, ReactNode][] = [
    ['Sample ID', <b key="s" className="font-semibold text-slate-900">{r.sample_id}</b>], ['Source', r.source],
    ['Spectral data', v?.range_cm1 ? `${v.points} points, ${v.range_cm1[0].toFixed(0)}–${v.range_cm1[1].toFixed(0)} cm⁻¹` : '—'],
    ['Excitation wavelength', exc ? `${exc} nm` : 'Not stated in file'], ['Spectra in file', String(r.inputs.n_spectra)],
    ['Reference library', library(r)],
    ['Processing', `Despike, ${String(params.baseline ?? 'als').toUpperCase()} baseline, ${params.smoothing ?? 'savgol'} smoothing, ${params.normalization ?? 'vector'} normalisation`],
  ]
  return (
    <dl className="grid overflow-hidden rounded-xl border border-slate-200 text-sm sm:grid-cols-2">
      {rows.map(([k, val]) => (
        <div key={k} className="flex gap-4 border-b border-slate-100 px-4 py-2.5 sm:odd:border-r">
          <dt className="w-40 flex-none text-slate-500">{k}</dt><dd className="min-w-0 text-slate-800">{val}</dd>
        </div>
      ))}
    </dl>
  )
}

/** 2 · Result summary: status, headline, one sentence on certainty, then the key numbers. */
function Answer({ r, v }: { r: FullReport; v: VisualSummary }) {
  const c = v.confidence
  const s = RESULT[c.level]
  const items = v.candidates.items
  const top = items[0]
  const gap = items.length > 1 ? items[0].score - items[1].score : null
  const passed = v.checks.filter(x => x.passed).length
  const kpis: [string, string, string?][] = [
    ['Closest reference', top?.name ?? '—'], ['Similarity', top ? top.score.toFixed(2) : '—', 'cosine, 0–1'],
    ['Margin to runner-up', gap != null ? gap.toFixed(2) : '—'], ['Quality checks', `${passed}/${v.checks.length}`, 'passed'],
    ['Confidence', c.label],
  ]
  return (
    <section aria-label="Answer">
      <div className="rounded-xl border border-accent-200 bg-mint p-5 sm:p-6" style={{ borderLeft: `5px solid ${s.color}` }}>
        <p className="text-[11px] font-bold tracking-[0.14em] uppercase" style={{ color: s.color }}>{s.word}</p>
        <p className="mt-1 text-xl font-semibold text-balance text-slate-900 sm:text-2xl" style={{ fontFamily: 'var(--font-serif)' }}>{r.explanation?.headline ?? r.brief.headline}</p>
        <p className="mt-2 text-sm leading-relaxed text-slate-600">{r.explanation?.how_sure ?? c.reason}</p>
      </div>
      <dl className="mt-3 grid grid-cols-2 overflow-hidden rounded-xl border border-slate-200 sm:grid-cols-5">
        {kpis.map(([k, val, note]) => (
          <div key={k} className="border-slate-200 px-4 py-3 sm:border-l sm:first:border-l-0">
            <dt className="text-[10.5px] tracking-wide text-slate-500 uppercase">{k}</dt>
            <dd className="mt-0.5 truncate text-lg font-semibold text-slate-900" title={val}>{val}</dd>
            {note && <dd className="text-[11px] text-slate-400">{note}</dd>}
          </div>
        ))}
      </dl>
    </section>
  )
}

/** Sample in front, reference behind, as filled curtains with the shared peaks marked on the sample. */
function overlay3d(v: VisualSummary): Data[] {
  const o = v.overlay
  const out = curtain(o.x, o.sample, 0, SAMPLE, 'Sample')
  if (o.reference) out.push(...curtain(o.reference.x, o.reference.y, 1, REFERENCE, `${o.reference_name} (reference)`))
  if (o.peaks.length) {
    const keep = spaced(o.peaks, o.peak_heights)
    out.push({
      type: 'scatter3d', mode: 'text+markers', name: 'Shared peaks', x: o.peaks, y: o.peaks.map(() => 0), z: o.peak_heights.map(h => h + 0.05),
      text: o.peaks.map((p, i) => (keep[i] ? String(p) : '')), textposition: 'top center', textfont: { size: 10, color: '#334155' },
      marker: { size: 3, color: '#334155' }, hovertemplate: 'Peak %{x:.0f} cm⁻¹<extra></extra>',
    } as Data)
  }
  return out
}

/** Processing stages stacked in depth, each scaled to its own range: raw → baseline → corrected → processed. */
function stages3d(r: FullReport): Data[] {
  const d = r.sections.spectrum.data
  const scale = (y: number[], ref = y) => { const lo = Math.min(...ref), hi = Math.max(...ref) - lo || 1; return y.map(q => (q - lo) / hi) }
  const corrected = d.raw.map((q, i) => q - d.baseline[i])
  const rows: [string, number[], string][] = [
    ['Raw counts', scale(d.raw), '#898781'], ['Fitted baseline', scale(d.baseline, d.raw), '#d97706'],
    ['Baseline removed', scale(corrected), '#1baf7a'], ['Processed', scale(d.processed), SAMPLE],
  ]
  return rows.flatMap(([name, z, color], k) => curtain(d.x, z, k, color, name, { fill: 0.6 }))
}

const STAGE_TICKS = { vals: [0, 1, 2, 3], text: ['Raw', 'Baseline', 'Corrected', 'Processed'] }

function Overlay({ v }: { v: VisualSummary }) {
  const o = v.overlay
  const traces: Data[] = [{
    x: o.x, y: o.sample, type: 'scatter', mode: 'lines', name: 'Sample', line: { color: SAMPLE, width: 2 },
    hovertemplate: 'Sample: %{y:.2f}<extra></extra>',
  }]
  if (o.reference) traces.push({
    x: o.reference.x, y: o.reference.y, type: 'scatter', mode: 'lines', name: `${o.reference_name} (reference)`,
    line: { color: REFERENCE, width: 2 }, opacity: 0.9, hovertemplate: `${o.reference_name}: %{y:.2f}<extra></extra>`,
  })
  const annotations = o.peaks.map((p, i) => ({
    x: p, y: o.peak_heights[i], text: `${p}`, showarrow: true, arrowhead: 0, arrowcolor: '#898781', ax: 0, ay: -22,
    font: { size: 11, color: '#52514e' },
  }))
  const xs = [...o.x, ...(o.reference?.x ?? [])]
  return (
    <section>
      <H n="3">Spectral comparison</H>
      <FigurePair
        two={<Figure data={traces} height={330} label="Sample spectrum overlaid on the best-matching reference spectrum"
          xTitle="Raman shift (cm⁻¹)" yTitle="Relative intensity"
          layout={{ hovermode: 'x unified', legend: { orientation: 'h', y: 1.12, x: 0, font: { size: 12 } }, margin: { t: 36, r: 16, l: 56, b: 52 },
            yaxis: { range: [-0.05, 1.18] }, annotations }} />}
        three={<Figure3D data={overlay3d(v)} height={340} label="Sample and reference spectra as a 3D waterfall with the shared peaks marked"
          xTitle="Raman shift (cm⁻¹)" yTitle="" zTitle="Relative intensity" aspect={{ x: 2.3, y: 0.8, z: 0.75 }}
          yTicks={{ vals: o.reference ? [0, 1] : [0], text: o.reference ? ['Sample', 'Reference'] : ['Sample'] }}
          xRange={[Math.min(...xs), Math.max(...xs)]} zRange={[0, 1.2]} />} />
      <Caption n="1">
        Processed sample spectrum{o.reference ? <> and the best-matching reference, {o.reference_name}</> : ''}, each scaled to its own maximum.
        {o.peaks.length > 0 && <> Labels mark {o.reference ? 'peaks found in both spectra' : 'the strongest peaks'} (cm⁻¹).</>} The 3D view places the spectra on separate tracks for side-by-side comparison.
      </Caption>
    </section>
  )
}

const REF_TYPE: Record<string, string> = { measured: 'Measured reference', synthetic: 'Literature-band reference' }

/**
 * 4 · Candidate ranking. Candidates are ordered by the ranking score (cosine similarity discounted when the overlap
 * covers too little of the reference or of the sample), so that score is the bar; similarity and coverage explain it.
 */
function Candidates({ v }: { v: VisualSummary }) {
  const { items, threshold } = v.candidates
  const th = 'px-3 py-2.5 text-[11px] font-semibold tracking-wider uppercase'
  return (
    <section>
      <H n="4">Candidate ranking</H>
      <div className="overflow-x-auto rounded-xl border border-slate-200">
        <table className="w-full min-w-[640px] text-sm">
          <thead>
            <tr className="border-b border-accent-200 bg-mint text-left text-accent-900">
              <th className={`${th} w-12`}>Rank</th><th className={th}>Candidate material</th>
              <th className={`${th} text-right`}>Similarity</th><th className={`${th} text-right`}>Coverage</th>
              <th className={`${th} w-[34%]`}>Ranking score</th>
            </tr>
          </thead>
          <tbody>
            {items.map((c, i) => {
              const rank = c.rank_score ?? c.score
              const below = c.score < threshold
              return (
                <tr key={c.name} className={`border-b border-slate-100 last:border-0 ${c.top ? 'bg-accent-50/60' : ''}`}>
                  <td className="px-3 py-2.5">
                    <span className={`inline-flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold tabular-nums ${c.top ? 'bg-accent-700 text-white' : 'bg-slate-100 text-slate-600'}`}>{i + 1}</span>
                  </td>
                  <td className="px-3 py-2.5">
                    <span className={`block ${c.top ? 'font-semibold text-slate-900' : 'text-slate-800'}`}>{c.name}</span>
                    {c.category && <span className="text-[11px] text-slate-500">{REF_TYPE[c.category] ?? c.category}</span>}
                  </td>
                  <td className={`px-3 py-2.5 text-right tabular-nums ${below ? 'text-slate-400' : 'text-slate-800'}`} title={below ? `Below the ${threshold.toFixed(2)} reporting threshold` : undefined}>
                    {c.score.toFixed(2)}{below && <sup className="ml-0.5 text-slate-400">†</sup>}
                  </td>
                  <td className="px-3 py-2.5 text-right text-slate-600 tabular-nums">{c.coverage != null ? `${Math.round(c.coverage * 100)}%` : '—'}</td>
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-3">
                      <div className="h-1.5 flex-1 rounded-full bg-slate-100">
                        <div className="h-full rounded-full" style={{ width: `${Math.min(1, rank) * 100}%`, background: c.top ? '#157f54' : '#86d3a8' }} />
                      </div>
                      <span className="w-9 text-right text-xs font-medium text-slate-700 tabular-nums">{rank.toFixed(2)}</span>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs leading-relaxed text-slate-500">
        <b className="font-medium text-slate-600">Similarity</b>: cosine similarity of band shape over the overlapping range (0 = unrelated, 1 = identical).{' '}
        <b className="font-medium text-slate-600">Coverage</b>: share of the reference's range that the measurement overlaps.{' '}
        <b className="font-medium text-slate-600">Ranking score</b>: similarity discounted when coverage is below 70% or the overlap holds under 60% of the sample's signal; candidates are ordered by it.{' '}
        † below the {threshold.toFixed(2)} similarity required to report a match.
      </p>
    </section>
  )
}

/** 5 · Quality control: every criterion with a PASS/FAIL label that does not rely on colour. */
function Checks({ v }: { v: VisualSummary }) {
  return (
    <section>
      <H n="5">Quality control</H>
      <ul className="grid gap-px overflow-hidden rounded-xl border border-slate-200 bg-slate-200 md:grid-cols-2">
        {v.checks.map(c => (
          <li key={c.id} className="flex items-start justify-between gap-4 bg-white px-4 py-3 md:last:odd:col-span-2">
            <span className="text-sm">
              <span className="font-medium text-slate-900">{c.label}</span>
              <span className="block text-xs text-slate-500">{c.detail}</span>
            </span>
            <span className="mt-0.5 flex-none rounded-full px-2.5 py-0.5 text-[10.5px] font-bold tracking-wider text-white" style={{ background: c.passed ? STATUS.good : STATUS.critical }}>
              {c.passed ? 'PASS' : 'FAIL'}<span className="sr-only">{c.passed ? ' — passed' : ' — not passed'}</span>
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}

function Appendix({ r }: { r: FullReport }) {
  const b = r.brief
  const e = r.explanation
  const notes = r.evaluation?.headline ? [...b.limitations, r.evaluation.headline] : b.limitations
  return (
    <details className="group rounded-xl border border-slate-200 bg-white">
      <summary className="flex cursor-pointer items-center justify-between gap-3 px-5 py-4">
        <span className="flex items-baseline gap-2 text-lg font-semibold text-accent-900" style={{ fontFamily: 'var(--font-serif)' }}>
          <span aria-hidden className="text-accent-600">A</span>Technical appendix
        </span>
        <span className="text-xs text-slate-500">Processing, peak table, methods and evidence <span aria-hidden className="ml-1 inline-block transition group-open:rotate-180">▾</span></span>
      </summary>
      <div className="space-y-8 border-t border-slate-200 px-5 py-6">
        <dl className="grid grid-cols-2 overflow-hidden rounded-xl border border-slate-200 lg:grid-cols-4">
          {b.metrics.map(m => (
            <div key={m.label} className="border-slate-200 px-4 py-3 lg:border-l lg:first:border-l-0">
              <dt className="text-[10.5px] tracking-wide text-slate-500 uppercase">{m.label}</dt>
              <dd className="mt-0.5 text-lg font-semibold text-slate-900">{m.value}</dd>
              {m.note && <dd className="text-[11px] text-slate-400">{m.note}</dd>}
            </div>
          ))}
        </dl>
        <section>
          <FigurePair
            two={<SpectrumPlot r={r.sections.spectrum.data} kind="processed" height={300} />}
            three={<Figure3D data={stages3d(r)} height={320} label="Processing stages from raw counts to processed spectrum, stacked in depth"
              xTitle="Raman shift (cm⁻¹)" yTitle="" zTitle="Scaled intensity" aspect={{ x: 2.3, y: 1.1, z: 0.7 }} yTicks={STAGE_TICKS}
              xRange={[Math.min(...r.sections.spectrum.data.x), Math.max(...r.sections.spectrum.data.x)]} zRange={[0, 1.05]} />} />
          <Caption n="2">Processed spectrum with every detected peak (left), and each processing stage on its own track, from raw counts through the fitted baseline to the final spectrum (right).</Caption>
        </section>
        <div className="grid gap-8 lg:grid-cols-2">
          <section>
            <h3 className="mb-2 text-xs font-semibold tracking-wider text-slate-600 uppercase">Table 1 · Principal peaks</h3>
            <table className="w-full text-sm">
              <thead><tr className="border-b border-accent-100 bg-mint text-left text-xs text-accent-900"><th className="px-2 py-2 font-semibold">Position (cm⁻¹)</th><th className="px-2 py-2 font-semibold">Rel. intensity</th><th className="px-2 py-2 font-semibold">Tentative region</th></tr></thead>
              <tbody>{b.peaks.map(p => (
                <tr key={p.position} className="border-b border-slate-100">
                  <td className="px-2 py-1.5 tabular-nums">{p.position.toFixed(0)}</td>
                  <td className="px-2 py-1.5 tabular-nums">{p.relative_height.toFixed(2)}</td>
                  <td className="px-2 py-1.5 text-slate-600">{p.assignment ?? '—'}</td>
                </tr>))}</tbody>
            </table>
          </section>
          <section>
            <h3 className="mb-2 text-xs font-semibold tracking-wider text-slate-600 uppercase">Method notes and limitations</h3>
            <Bullets items={notes} />
          </section>
        </div>
        {e && (
          <section>
            <h3 className="mb-2 text-xs font-semibold tracking-wider text-slate-600 uppercase">Evidence behind the summary</h3>
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
  const found = (e?.what_we_found.map(f => f.text) ?? r.brief.findings).slice(0, 4)
  const next = (e?.next_steps ?? r.brief.recommendations).slice(0, 4)
  const meta: [string, string][] = [['Report ID', r.brief.report_id], ['Issued', when], ['Software', `RamanReach ${r.software_version}`], ['Classification', 'Research use']]
  return (
    <article aria-label="Analysis report" className="fade-up mx-auto mt-6 max-w-6xl overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-[0_24px_60px_-36px_rgba(15,102,68,0.35)]">
      <div aria-hidden className="h-1.5 bg-gradient-to-r from-accent-900 via-accent-600 to-accent-400" />
      <header className="border-b-2 border-accent-900/80 px-6 pt-6 pb-5 sm:px-10">
        <div className="flex flex-wrap items-start justify-between gap-6">
          <div>
            <p className="kicker">RamanReach · Spectroscopy Research Lab</p>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight text-slate-900 sm:text-[28px]" style={{ fontFamily: 'var(--font-serif)' }}>Spectrum analysis report</h1>
            <p className="mt-1 text-sm text-slate-500">Automated processing, peak detection and reference comparison · <span className="font-medium text-slate-700">{r.sample_id}</span></p>
          </div>
          <Actions r={r} onNew={onNew} />
        </div>
        <dl className="mt-5 grid grid-cols-2 gap-x-6 gap-y-2 text-xs sm:grid-cols-4">
          {meta.map(([k, val]) => <div key={k}><dt className="text-slate-500">{k}</dt><dd className="font-medium text-slate-800">{val}</dd></div>)}
        </dl>
      </header>

      <div className="space-y-10 px-6 py-8 sm:px-10">
        <section><H n="1">Sample information</H><SampleInfo r={r} /></section>
        {v && <section><H n="2">Result summary</H><Answer r={r} v={v} /></section>}
        {v && <Overlay v={v} />}
        {v && (
          <div className="space-y-10">
            <Candidates v={v} />
            <Checks v={v} />
          </div>
        )}
        <div className="grid gap-10 lg:grid-cols-2">
          <section><H n="6">Interpretation</H><Bullets items={found} /></section>
          <section><H n="7">Recommendations</H><Bullets items={next} /></section>
        </div>
        <Appendix r={r} />
      </div>
    </article>
  )
}
