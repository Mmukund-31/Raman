import { useState } from 'react'
import type { Data } from 'plotly.js'
import { PALETTE, field } from '../components/theme'
import { AddToReport, Busy, Chart, Checks, DataBadge, Insights, Notes, Plain } from '../components/Research'
import { runTranslation } from '../services/research'
import type { Study, Translation } from '../types/research'

const METRICS: [string, string][] = [
  ['rmse', 'RMSE'], ['mae', 'MAE'], ['cosine', 'Cosine'], ['spectral_angle_rad', 'Spectral angle (rad)'], ['dtw', 'DTW'],
  ['peak_position_error_cm1', 'Peak-position error (cm⁻¹)'], ['peak_preservation_rate', 'Peak preservation rate'], ['intensity_ratio_error', 'Relative-height error'],
]

export function TranslationEval({ onAdd }: { onAdd: (s: Study) => void }) {
  const [nSpec, setNSpec] = useState(16)
  const [shift, setShift] = useState(6)
  const [res, setRes] = useState<Translation | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const run = async () => {
    setBusy(true); setError('')
    try {
      setRes(await runTranslation({ n_specimens: nSpec, source_steps: [
        { kind: 'axis_shift', params: { delta_cm1: shift } }, { kind: 'broadening', params: { sigma_cm1: 3 } }, { kind: 'baseline_distortion', params: { amplitude_frac: 0.8 } }] }))
    } catch (e) { setError((e as Error).message); setRes(null) }
    setBusy(false)
  }
  const names = res ? Object.keys(res.fidelity) : []
  const plot: Data[] = res?.example.target ? [
    { x: res.example.x, y: res.example.target, type: 'scatter', mode: 'lines', name: 'target (reference condition)', line: { color: '#000', width: 2 } },
    { x: res.example.x, y: res.example.source_resampled!, type: 'scatter', mode: 'lines', name: 'source, resampled only', line: { color: PALETTE[1], width: 1.2 } },
    ...Object.entries(res.example.translated).filter(([k]) => k === 'shift_correction').map(([k, v]) => ({ x: res.example.x, y: v, type: 'scatter' as const, mode: 'lines' as const, name: `translated (${k})`, line: { color: PALETTE[2], width: 1.2 } })),
  ] : []

  return (
    <div className="space-y-6">
      <section className="rounded bg-white p-4 shadow-sm">
        <h2 className="text-xl font-semibold">Spectral Translation Evaluation</h2>
        <p className="mb-3 text-sm text-slate-700">
          Can a spectrum from one acquisition condition be mapped to something comparable with another, without erasing real peaks? A translated spectrum is <b>never</b> an actual measurement from the target instrument.
          With no paired measured data available, this runs a <b>controlled-perturbation benchmark</b> on synthetic spectra against simple, transparent baselines. A neural translator is deliberately not trained.
        </p>
        <div className="flex flex-wrap items-end gap-4 text-sm">
          <label>Specimens per material<input type="number" min={6} max={40} className={field} value={nSpec} onChange={e => setNSpec(Number(e.target.value))} /></label>
          <label>Injected source axis shift (cm⁻¹)<input type="number" className={field} value={shift} onChange={e => setShift(Number(e.target.value))} /></label>
          <button onClick={run} disabled={busy} className="rounded bg-blue-700 px-5 py-2 font-medium text-white hover:bg-blue-800 disabled:opacity-50">Run evaluation</button>
        </div>
        <Busy busy={busy} error={error} />
      </section>

      {res && (
        <>
          <Notes items={[res.warning, ...res.limitations, `Neural translation: ${res.neural_translation.status}. ${res.neural_translation.reason}`]} />
          <Chart traces={plot} title="Example pair (processed)" xTitle="Raman shift (cm⁻¹)" yTitle="Normalized intensity (a.u.)" dc={res.data_class}
            condition={`source = target + ${res.source_description.steps.map(s => s.kind).join(', ')}; coarser source grid ${res.source_description.grid_step_cm1} cm⁻¹`} />
          <section className="overflow-auto rounded bg-white p-4 text-sm shadow-sm">
            <h3 className="font-semibold">Fidelity to the target ({res.n_evaluation_pairs} held-out pairs) <DataBadge dc={res.data_class} /></h3>
            <p className="text-xs text-slate-600">Calibration parameters were estimated from a separate standard ({res.calibration_standard}); estimated shift {res.fitted_parameters.shift_correction.shift_cm1.toFixed(2)} cm⁻¹. “Improved” = better than resampling only on more than half the pairs.</p>
            <table className="mt-2 w-full"><thead><tr className="text-left"><th>Metric</th>{names.map(n => <th key={n}>{n}</th>)}</tr></thead>
              <tbody>{METRICS.map(([k, l]) => (
                <tr key={k} className="border-t"><td>{l}</td>{names.map(n => {
                  const a = res.fidelity[n].aggregate[k]; const c = res.comparison_vs_resample_only[n]?.[k]
                  return <td key={n}>{a ? a.mean.toFixed(3) : '—'}{c && <span className={c.improved ? ' text-emerald-700' : ' text-red-700'}> {c.improved ? '▲ improved' : '✕ not improved'}</span>}</td>
                })}</tr>))}</tbody></table>
            <p className="mt-1 text-xs text-slate-600">Cosine similarity alone does not show successful translation: check peak-position error and peak preservation too.</p>
          </section>
          {res.downstream && (
            <section className="rounded bg-white p-4 text-sm shadow-sm">
              <h3 className="font-semibold">Downstream classification (accuracy / macro-F1)</h3>
              <ul className="list-disc pl-5">{Object.entries(res.downstream).map(([k, v]) => typeof v === 'string' ? <li key={k}>{v}</li> :
                <li key={k}>{k}: {v.accuracy.toFixed(2)} / {v.macro_f1.toFixed(2)} (n = {v.n})</li>)}</ul>
            </section>)}
          <Plain r={res} /><Insights items={res.insights} /><Checks items={res.self_checks} />
          <AddToReport study={{ kind: 'translation', title: 'Spectral translation (controlled perturbation)', result: res }} onAdd={onAdd} />
        </>
      )}
    </div>
  )
}
