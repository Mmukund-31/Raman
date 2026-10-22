import { useState } from 'react'
import { fetchReportHtml } from '../services/api'
import type { Result } from '../types'

function download(name: string, text: string, type: string) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([text], { type }))
  a.download = name
  a.click()
  URL.revokeObjectURL(a.href)
}

export function Results({ r }: { r: Result }) {
  const [err, setErr] = useState('')
  const inconclusive = r.status === 'inconclusive'
  const report = async () => {
    try { setErr(''); download(`ramanreach-${r.sample_id}.html`, await fetchReportHtml(r), 'text/html') }
    catch (e) { setErr((e as Error).message) }
  }
  const csv = () => download(`ramanreach-${r.sample_id}-processed.csv`,
    'raman_shift_cm1,raw,baseline,processed\n' + r.x.map((x, i) => `${x},${r.raw[i]},${r.baseline[i]},${r.processed[i]}`).join('\n'), 'text/csv')

  return (
    <section aria-label="Results" className="space-y-4">
      <div role="status" className={`rounded border-2 p-4 ${inconclusive ? 'border-amber-600 bg-amber-50' : 'border-emerald-700 bg-emerald-50'}`}>
        <p className="text-lg font-semibold">
          {inconclusive ? '⚠ INCONCLUSIVE — evidence is inadequate to claim a match' : '✔ Quality checks passed — candidate matches shown'}
        </p>
        <p className="text-sm">Sample <b>{r.sample_id}</b> · {r.source} · SNR estimate {r.snr}</p>
        {r.quality_warnings.length > 0 && (
          <ul className="mt-2 list-disc pl-5 text-sm">{r.quality_warnings.map(w => <li key={w}>{w}</li>)}</ul>
        )}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded bg-white p-4 shadow-sm">
          <h3 className="font-semibold">Reference comparison</h3>
          <p className="mb-2 text-xs text-slate-600">Cosine similarity (−1 to 1). Not a probability of identification.</p>
          <table className="w-full text-sm">
            <thead><tr className="text-left"><th>Reference</th><th>Score</th><th>Coverage</th></tr></thead>
            <tbody>{r.matches.map((m, i) => (
              <tr key={m.reference_id} className={!inconclusive && i === 0 ? 'font-semibold' : ''}>
                <td>{m.name}{!inconclusive && i === 0 ? ' (best candidate)' : ''}</td><td>{m.score.toFixed(3)}</td><td>{Math.round(m.coverage * 100)}%</td>
              </tr>))}</tbody>
          </table>
        </div>
        <div className="rounded bg-white p-4 shadow-sm">
          <h3 className="font-semibold">Detected peaks ({r.peaks.length})</h3>
          <div className="max-h-56 overflow-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left"><th>Position (cm⁻¹)</th><th>Rel. height</th><th>Flag</th></tr></thead>
              <tbody>{r.peaks.map(p => (
                <tr key={p.position}><td>{p.position.toFixed(1)}</td><td>{p.relative_height.toFixed(2)}</td><td>{p.near_boundary ? 'near boundary' : ''}</td></tr>))}</tbody>
            </table>
          </div>
        </div>
      </div>

      <details className="rounded bg-white p-4 text-sm shadow-sm">
        <summary className="cursor-pointer font-semibold">Processing parameters & limitations</summary>
        <pre className="mt-2 overflow-auto text-xs">{JSON.stringify(r.parameters, null, 2)}</pre>
        <ul className="list-disc pl-5">{r.limitations.map(l => <li key={l}>{l}</li>)}</ul>
      </details>

      <div className="flex flex-wrap gap-3">
        <button onClick={report} className="rounded bg-blue-700 px-4 py-2 text-white hover:bg-blue-800">Download report (HTML)</button>
        <button onClick={csv} className="rounded border border-blue-700 px-4 py-2 text-blue-700 hover:bg-blue-50">Download processed CSV</button>
      </div>
      {err && <p role="alert" className="text-red-700">{err}</p>}
    </section>
  )
}
