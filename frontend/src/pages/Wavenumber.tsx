import { useEffect, useState } from 'react'
import type { Data } from 'plotly.js'
import { PALETTE, field } from '../components/theme'
import { AddToReport, Busy, Chart, Checks, DataBadge, Insights, Notes, Plain } from '../components/Research'
import { getExamples } from '../services/api'
import { runMatrix, runSweep } from '../services/research'
import type { Example } from '../types'
import type { Matrix, Study, Sweep } from '../types/research'

const KINDS: [string, string][] = [
  ['axis_shift', 'Global axis shift (calibration error)'], ['signal_shift', 'Global peak shift (physical change)'],
  ['axis_warp', 'Nonlinear axis warp (calibration error)'], ['broadening', 'Peak broadening'],
  ['baseline_distortion', 'Baseline distortion'], ['intensity_scale', 'Intensity scaling'], ['noise', 'Noise level'],
]

/** Up to n evenly spaced items, always including the first and last. */
function pick<T>(a: T[], n: number): T[] {
  if (a.length <= n) return a
  return Array.from({ length: n }, (_, i) => a[Math.round((i * (a.length - 1)) / (n - 1))])
}

export function Wavenumber({ onAdd }: { onAdd: (s: Study) => void }) {
  const [examples, setExamples] = useState<Example[]>([])
  const [example, setExample] = useState('demo_paracetamol_synthetic')
  const [kind, setKind] = useState('axis_shift')
  const [levels, setLevels] = useState('')
  const [withModel, setWithModel] = useState(true)
  const [res, setRes] = useState<Sweep | null>(null)
  const [matrix, setMatrix] = useState<Matrix | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { getExamples().then(setExamples).catch(e => setError(`Cannot reach API: ${e.message}`)) }, [])

  const run = async () => {
    setBusy(true); setError(''); setMatrix(null)
    try {
      const lv = levels.trim() ? levels.split(',').map(Number) : undefined
      if (lv?.some(Number.isNaN)) throw new Error('Levels must be comma-separated numbers.')
      setRes(await runSweep({ spectrum: { example_id: example }, kind, levels: lv, with_model: withModel }))
    } catch (e) { setError((e as Error).message); setRes(null) }
    setBusy(false)
  }
  const runMat = async () => {
    setBusy(true); setError('')
    try { setMatrix(await runMatrix({ example_id: example })) } catch (e) { setError((e as Error).message) }
    setBusy(false)
  }

  const rows = res?.rows.filter(r => !r.error) ?? []
  const colour = (i: number) => PALETTE[i % PALETTE.length]
  const cond = res ? `${res.label}; everything else held fixed; sample ${res.sample}` : ''
  const overlay: Data[] = res ? [
    { x: res.baseline_x, y: res.baseline_processed, type: 'scatter', mode: 'lines', name: 'unperturbed', line: { color: '#000', dash: 'dot', width: 2 } },
    ...pick(rows.filter(r => r.level !== res.neutral_level), 4)
      .map((r, i) => ({ x: r.processed_x, y: r.processed, type: 'scatter' as const, mode: 'lines' as const, name: `${r.level} ${res.level_unit}`, line: { color: colour(i), width: 1.2 } })),
  ] : []
  const sim: Data[] = res ? [{
    x: rows.map(r => r.level), y: rows.map(r => r.truth_score), type: 'scatter', mode: 'lines+markers', name: 'similarity to true reference',
    marker: { color: rows.map(r => (r.correct ? '#009E73' : r.status === 'ok' ? '#D55E00' : '#999')), size: 9 }, line: { color: '#0072B2' },
    text: rows.map(r => `${r.status}; top match ${r.top1}`), hoverinfo: 'text+x+y',
  }] : []
  const pcaTraces: Data[] = res ? [
    { x: res.reference_pca.scores.map(s => s[0]), y: res.reference_pca.scores.map(s => s[1]), text: res.reference_pca.ids, type: 'scatter', mode: 'text+markers', name: 'synthetic references', marker: { size: 10, color: '#444' }, textposition: 'top center' },
    { x: rows.map(r => r.pca_position[0]), y: rows.map(r => r.pca_position[1]), text: rows.map(r => `${r.level}`), type: 'scatter', mode: 'lines+markers', name: 'perturbed spectrum', marker: { color: '#D55E00' }, line: { color: '#D55E00', width: 1 } },
  ] : []

  return (
    <div className="space-y-6">
      <section className="rounded bg-white p-4 shadow-sm">
        <h2 className="text-xl font-semibold">Wavenumber Sensitivity Lab</h2>
        <p className="mb-3 text-sm text-slate-700">
          Shift the Raman-shift axis (or apply another perturbation) in controlled steps and watch what the analysis does. Everything here is <b>simulated</b>:
          it tests the software, not an instrument. The test range is yours to configure and is not an instrument tolerance.
        </p>
        <div className="grid gap-3 text-sm md:grid-cols-4">
          <label>Spectrum<select className={field} value={example} onChange={e => setExample(e.target.value)}>
            {examples.map(x => <option key={x.sample_id} value={x.sample_id}>{x.sample_id}</option>)}</select></label>
          <label>Perturbation<select className={field} value={kind} onChange={e => setKind(e.target.value)}>
            {KINDS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
          <label>Levels (comma-separated, blank = default range)<input className={field} placeholder="e.g. -10,-5,0,5,10" value={levels} onChange={e => setLevels(e.target.value)} /></label>
          <label className="self-end"><input type="checkbox" checked={withModel} onChange={e => setWithModel(e.target.checked)} /> Also show a demo classifier (trained on simulated data)</label>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <button onClick={run} disabled={busy} className="rounded bg-blue-700 px-5 py-2 font-medium text-white hover:bg-blue-800 disabled:opacity-50">Run sweep</button>
          <button onClick={runMat} disabled={busy} className="rounded border border-slate-400 px-4 py-2 hover:bg-slate-100 disabled:opacity-50">Run experiment matrix (one parameter at a time)</button>
        </div>
        <Busy busy={busy} error={error} />
      </section>

      {matrix && (
        <section className="rounded bg-white p-4 text-sm shadow-sm">
          <h3 className="font-semibold">Experiment matrix — {matrix.sample} <DataBadge dc="simulated" /></h3>
          <p className="text-xs text-slate-600">Held constant: {matrix.held_constant}. “First failure” is where the pipeline stopped giving a confirmed correct answer.</p>
          <table className="mt-2 w-full"><thead><tr className="text-left"><th>Parameter varied</th><th>Class</th><th>Tested</th><th>First failure</th></tr></thead>
            <tbody>{matrix.experiments.map(e => (
              <tr key={e.kind} className="border-t"><td>{e.label}</td><td>{e.class}</td><td>{Math.min(...e.levels)} to {Math.max(...e.levels)} {e.unit}</td>
                <td>{Object.keys(e.first_failure).length ? Object.entries(e.first_failure).map(([s, f]) => `${s} ${e.neutral}: ${f.level} (${f.reason})`).join('; ') : 'none in tested range'}</td></tr>))}</tbody></table>
        </section>
      )}

      {res && (
        <>
          <Notes items={[res.distinction_note, ...res.limitations]} />
          <div className="grid gap-4 lg:grid-cols-2">
            <Chart traces={overlay} title="Processed spectra: unperturbed vs perturbed" xTitle="Raman shift (cm⁻¹)" yTitle="Normalized intensity (a.u.)" dc={res.data_class} condition={cond} />
            <Chart traces={sim} title="Similarity to the true reference vs perturbation size" xTitle={`${res.label} (${res.level_unit})`} yTitle="Cosine similarity" dc={res.data_class}
              condition={`${cond}. Green = confirmed correct, orange = ok but wrong, grey = inconclusive`} />
            <Chart traces={pcaTraces} title="Position in the reference-library PCA plane" xTitle={`PC1 (${(100 * res.reference_pca.explained_variance_ratio[0]).toFixed(0)}% of reference variance)`}
              yTitle="PC2" dc={res.data_class} condition={res.reference_pca.note} />
            <section className="rounded bg-white p-4 text-sm shadow-sm">
              <h3 className="font-semibold">Where does it become unreliable?</h3>
              {Object.keys(res.first_failure).length ? (
                <ul className="list-disc pl-5">{Object.entries(res.first_failure).map(([s, f]) => <li key={s}>{s} the unperturbed value ({res.neutral_level}): first failure at <b>{f.level} {res.level_unit}</b> ({f.reason}).</li>)}</ul>
              ) : <p>No failure in the tested range; the limit was not found.</p>}
              <p className="mt-2 text-xs text-slate-600">“Inconclusive” can occur while the top match is still the true material, because the quality gate is stricter than the ranking.</p>
            </section>
          </div>
          <section className="overflow-auto rounded bg-white p-4 text-sm shadow-sm">
            <table className="w-full"><thead><tr className="text-left"><th>Level ({res.level_unit})</th><th>Peak shift found</th><th>Similarity to truth</th><th>Top match</th><th>Status</th><th>Correct?</th>{withModel && <th>Demo classifier (confidence)</th>}</tr></thead>
              <tbody>{rows.map(r => (
                <tr key={r.level} className="border-t"><td>{r.level}</td>
                  <td>{r.mean_peak_displacement_cm1 == null ? '—' : `${r.mean_peak_displacement_cm1.toFixed(1)} cm⁻¹ (${r.n_baseline_peaks_found}/${r.n_baseline_peaks} peaks)`}</td>
                  <td>{r.truth_score?.toFixed(2)}</td><td>{r.top1}</td><td>{r.status}</td><td>{r.correct ? 'yes' : 'no'}</td>
                  {withModel && <td>{r.model_prediction ? `${r.model_prediction.label} (${(100 * r.model_prediction.confidence).toFixed(0)}%)` : '—'}</td>}</tr>))}</tbody></table>
            {withModel && <p className="mt-1 text-xs text-slate-600">The demo classifier is trained on simulated data only; its confidence is not evidence of correctness.</p>}
          </section>
          <Plain r={res} /><Insights items={res.insights} /><Checks items={res.self_checks} />
          <AddToReport study={{ kind: 'sweep', title: `Sensitivity: ${res.label} (${res.sample})`, result: res }} onAdd={onAdd} />
        </>
      )}
    </div>
  )
}
