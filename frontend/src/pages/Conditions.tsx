import { useEffect, useState } from 'react'
import type { Data } from 'plotly.js'
import { PALETTE, field } from '../components/theme'
import { AddToReport, Busy, Chart, DataBadge, Insights, Notes, Plain } from '../components/Research'
import { getExamples } from '../services/api'
import { compareConditions, excitationInfo, type ExperimentIn } from '../services/research'
import type { Example } from '../types'
import type { Conditions, ExcitationInfo, Study } from '../types/research'

type Meta = Record<string, string>
const META_FIELDS: [string, string][] = [
  ['temperature', 'Temperature value'], ['excitation_nm', 'Excitation wavelength (nm)'], ['laser_power', 'Laser power value'],
  ['exposure_s', 'Exposure / integration time (s)'], ['incidence_angle_deg', 'Incidence angle from surface normal (°)'],
  ['collection_angle_deg', 'Collection angle (°)'], ['spot_diameter_um', 'Spot diameter (µm, optional)'],
  ['geometry', 'Collection geometry (text)'], ['instrument', 'Instrument ID (text)'],
]

function toMeta(m: Meta): Record<string, string | number> {
  const out: Record<string, string | number> = {}
  for (const [k, v] of Object.entries(m)) {
    if (v === '') continue
    out[k] = ['geometry', 'instrument', 'temperature_unit', 'laser_power_unit'].includes(k) ? v : Number(v)
  }
  return out
}

function MetaForm({ m, set }: { m: Meta; set: (m: Meta) => void }) {
  const upd = (k: string, v: string) => set({ ...m, [k]: v })
  return (
    <div className="grid gap-2 text-sm sm:grid-cols-2 md:grid-cols-3">
      {META_FIELDS.map(([k, l]) => (
        <label key={k}>{l}
          <div className="flex gap-1">
            <input className={field} value={m[k] ?? ''} onChange={e => upd(k, e.target.value)} />
            {k === 'temperature' && <select className="rounded border border-slate-300" aria-label="Temperature unit" value={m.temperature_unit ?? 'K'} onChange={e => upd('temperature_unit', e.target.value)}><option>K</option><option>C</option></select>}
            {k === 'laser_power' && <select className="rounded border border-slate-300" aria-label="Laser power unit" value={m.laser_power_unit ?? 'mW'} onChange={e => upd('laser_power_unit', e.target.value)}><option>W</option><option>mW</option><option>uW</option></select>}
          </div>
        </label>
      ))}
    </div>
  )
}

interface ExpForm { label: string; mode: 'simulate' | 'upload'; kind: string; p1: string; p2: string; p3: string; file: File | null; meta: Meta }
const blank = (i: number): ExpForm => ({ label: `Condition ${i + 1}`, mode: 'simulate', kind: 'temperature', p1: '50', p2: '-0.02', p3: '0.01', file: null, meta: {} })

export function ConditionsLab({ onAdd }: { onAdd: (s: Study) => void }) {
  const [examples, setExamples] = useState<Example[]>([])
  const [example, setExample] = useState('demo_paracetamol_synthetic')
  const [base, setBase] = useState<Meta>({ temperature: '25', temperature_unit: 'C', excitation_nm: '532', laser_power: '10', laser_power_unit: 'mW', exposure_s: '1' })
  const [exps, setExps] = useState<ExpForm[]>([blank(0)])
  const [res, setRes] = useState<Conditions | null>(null)
  const [exc, setExc] = useState<ExcitationInfo | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { getExamples().then(setExamples).catch(e => setError(`Cannot reach API: ${e.message}`)) }, [])
  useEffect(() => {
    const nm = Number(base.excitation_nm)
    if (!nm) return
    let live = true
    excitationInfo(nm).then(i => { if (live) setExc(i) }).catch(() => { if (live) setExc(null) })
    return () => { live = false }
  }, [base.excitation_nm])

  const upd = (i: number, patch: Partial<ExpForm>) => setExps(es => es.map((e, k) => (k === i ? { ...e, ...patch } : e)))

  const run = async () => {
    setBusy(true); setError('')
    try {
      const baseline: ExperimentIn = { label: 'Baseline', data_class: 'synthetic_example', metadata: toMeta(base), spectrum: { example_id: example } }
      const experiments: ExperimentIn[] = await Promise.all(exps.map(async e => {
        if (e.mode === 'upload') {
          if (!e.file) throw new Error(`'${e.label}': choose a CSV file.`)
          return { label: e.label, data_class: 'measured', metadata: toMeta(e.meta), spectrum: { csv_text: await e.file.text(), excitation_nm: Number(e.meta.excitation_nm) || undefined } }
        }
        const params: Record<string, number> =
          e.kind === 'temperature' ? { delta_T_K: Number(e.p1), shift_coeff_cm1_per_K: Number(e.p2), broadening_coeff_cm1_per_K: Number(e.p3) }
            : e.kind === 'laser_power' ? { factor: Number(e.p1) } : e.kind === 'broadening' ? { sigma_cm1: Number(e.p1) }
              : e.kind === 'noise' ? { sigma_frac: Number(e.p1) } : { amplitude_frac: Number(e.p1) }
        return { label: e.label, data_class: 'simulated', metadata: {}, simulate: [{ kind: e.kind, params }] }
      }))
      setRes(await compareConditions(baseline, experiments))
    } catch (e) { setError((e as Error).message); setRes(null) }
    setBusy(false)
  }

  const c = res
  const overlay = (key: 'raw' | 'processed'): Data[] => c ? [
    { x: key === 'raw' ? c.baseline.raw_x : c.baseline.x, y: c.baseline[key], type: 'scatter', mode: 'lines', name: 'Baseline', line: { color: '#000', width: 2 } },
    ...c.experiments.map((e, i) => ({ x: key === 'raw' ? e.raw_x : e.x, y: e[key], type: 'scatter' as const, mode: 'lines' as const, name: e.label, line: { color: PALETTE[i % PALETTE.length], width: 1.2 } })),
  ] : []
  const diff: Data[] = c ? c.experiments.map((e, i) => ({ x: e.difference_x, y: e.difference, type: 'scatter' as const, mode: 'lines' as const, name: `${e.label} − baseline`, line: { color: PALETTE[i % PALETTE.length] } })) : []
  const dcOf = c?.data_class ?? 'simulated'

  return (
    <div className="space-y-6">
      <section className="rounded bg-white p-4 shadow-sm">
        <h2 className="text-xl font-semibold">Experimental Conditions Lab</h2>
        <p className="mb-3 text-sm text-slate-700">
          Compare one sample under different recorded conditions. You can <b>simulate</b> temperature, laser power and other instrument effects (clearly labelled), or
          <b> upload measured CSV files</b> with their metadata. Excitation wavelength and incidence/collection angle <b>cannot be simulated</b>: no universal law exists, so
          upload real measurements for those.
        </p>
        <h3 className="font-semibold">Baseline</h3>
        <label className="text-sm">Sample
          <select className={`${field} md:w-1/3`} value={example} onChange={e => setExample(e.target.value)}>{examples.map(x => <option key={x.sample_id}>{x.sample_id}</option>)}</select>
        </label>
        <div className="mt-2"><MetaForm m={base} set={setBase} /></div>
        {exc && exc.excitation_nm === Number(base.excitation_nm) && <p className="mt-2 rounded bg-slate-50 p-2 text-xs"><b>{exc.laser_color} laser, {exc.excitation_nm} nm:</b> Stokes shifts of +200 to +3000 cm⁻¹ are scattered at {exc.stokes_wavelength_nm[0].toFixed(0)}–{exc.stokes_wavelength_nm[1].toFixed(0)} nm; anti-Stokes shifts of the same size at {exc.anti_stokes_wavelength_nm[1].toFixed(0)}–{exc.anti_stokes_wavelength_nm[0].toFixed(0)} nm (λ = 10⁷ / (10⁷/λ₀ ∓ shift)). {exc.explanation}</p>}
      </section>

      {exps.map((e, i) => (
        <section key={i} className="rounded bg-white p-4 shadow-sm">
          <div className="flex flex-wrap items-end gap-3 text-sm">
            <label>Label<input className={field} value={e.label} onChange={ev => upd(i, { label: ev.target.value })} /></label>
            <label>Source<select className={field} value={e.mode} onChange={ev => upd(i, { mode: ev.target.value as ExpForm['mode'] })}><option value="simulate">Simulate from baseline</option><option value="upload">Upload measured CSV</option></select></label>
            {e.mode === 'simulate' ? (
              <>
                <label>Effect<select className={field} value={e.kind} onChange={ev => upd(i, { kind: ev.target.value })}>
                  <option value="temperature">Temperature (user-specified coefficients)</option><option value="laser_power">Laser power</option>
                  <option value="broadening">Peak broadening</option><option value="noise">Noise</option><option value="baseline_distortion">Baseline distortion</option></select></label>
                <label>{e.kind === 'temperature' ? 'ΔT (K)' : e.kind === 'laser_power' ? 'Power ratio (×)' : e.kind === 'broadening' ? 'σ (cm⁻¹)' : 'Fraction of range'}
                  <input className={field} value={e.p1} onChange={ev => upd(i, { p1: ev.target.value })} /></label>
                {e.kind === 'temperature' && <>
                  <label>Peak shift coeff (cm⁻¹/K, assumed)<input className={field} value={e.p2} onChange={ev => upd(i, { p2: ev.target.value })} /></label>
                  <label>Broadening coeff (cm⁻¹/K, assumed)<input className={field} value={e.p3} onChange={ev => upd(i, { p3: ev.target.value })} /></label></>}
              </>
            ) : (
              <label>CSV<input type="file" accept=".csv" className={field} onChange={ev => upd(i, { file: ev.target.files?.[0] ?? null })} /></label>
            )}
            {exps.length > 1 && <button className="text-red-700 underline" onClick={() => setExps(es => es.filter((_, k) => k !== i))}>Remove</button>}
          </div>
          {e.mode === 'upload' && <div className="mt-2"><MetaForm m={e.meta} set={m => upd(i, { meta: m })} /></div>}
          {e.mode === 'simulate' && e.kind === 'temperature' && <p className="mt-1 text-xs text-slate-600">Coefficients are your assumptions, not material data; real temperature effects are material- and mode-specific.</p>}
        </section>
      ))}
      <div className="flex flex-wrap gap-2">
        {exps.length < 4 && <button className="rounded border border-slate-400 px-3 py-2 text-sm hover:bg-slate-100" onClick={() => setExps(es => [...es, blank(es.length)])}>+ Add condition</button>}
        <button onClick={run} disabled={busy} className="rounded bg-blue-700 px-5 py-2 font-medium text-white hover:bg-blue-800 disabled:opacity-50">Compare</button>
      </div>
      <Busy busy={busy} error={error} />

      {c && (
        <>
          <Notes items={c.limitations} />
          <div className="grid gap-4 lg:grid-cols-2">
            <Chart traces={overlay('raw')} title="Raw spectra (overlay)" xTitle="Raman shift (cm⁻¹)" yTitle="Intensity (counts)" dc={dcOf} condition="baseline vs listed conditions" />
            <Chart traces={overlay('processed')} title="Processed spectra (overlay)" xTitle="Raman shift (cm⁻¹)" yTitle="Normalized intensity (a.u.)" dc={dcOf} condition="same preprocessing for all" />
            <Chart traces={diff} title="Difference: condition − baseline (processed)" xTitle="Raman shift (cm⁻¹)" yTitle="Δ normalized intensity (a.u.)" dc={dcOf} condition="positive = stronger than baseline" />
            <section className="overflow-auto rounded bg-white p-4 text-sm shadow-sm">
              <h3 className="font-semibold">Side by side</h3>
              <table className="w-full"><thead><tr className="text-left"><th></th><th>Baseline</th>{c.experiments.map(e => <th key={e.label}>{e.label}</th>)}</tr></thead>
                <tbody>
                  <tr className="border-t"><td>Data</td><td><DataBadge dc={c.baseline.data_class} /></td>{c.experiments.map(e => <td key={e.label}><DataBadge dc={e.data_class} /></td>)}</tr>
                  <tr className="border-t"><td>Parameter changed</td><td>—</td>{c.experiments.map(e => <td key={e.label}>{e.changed_parameters.join(', ') || 'none recorded'}</td>)}</tr>
                  <tr className="border-t"><td>Design</td><td>—</td>{c.experiments.map(e => <td key={e.label}>{e.design}</td>)}</tr>
                  <tr className="border-t"><td>Held equal</td><td>—</td>{c.experiments.map(e => <td key={e.label}>{e.constant_parameters.join(', ') || '—'}</td>)}</tr>
                  <tr className="border-t"><td>Not recorded in both</td><td>—</td>{c.experiments.map(e => <td key={e.label}>{e.unrecorded_parameters.join(', ') || '—'}</td>)}</tr>
                  <tr className="border-t"><td>Similarity to baseline</td><td>1</td>{c.experiments.map(e => <td key={e.label}>{e.similarity_to_baseline.toFixed(3)}</td>)}</tr>
                  <tr className="border-t"><td>Mean peak shift (cm⁻¹)</td><td>—</td>{c.experiments.map(e => <td key={e.label}>{e.mean_delta_position_cm1?.toFixed(2) ?? '—'}</td>)}</tr>
                  <tr className="border-t"><td>Mean width change (cm⁻¹)</td><td>—</td>{c.experiments.map(e => <td key={e.label}>{e.mean_delta_fwhm_cm1?.toFixed(2) ?? '—'}</td>)}</tr>
                  <tr className="border-t"><td>Median peak-height ratio</td><td>1</td>{c.experiments.map(e => <td key={e.label}>{e.median_height_ratio?.toFixed(2) ?? '—'}</td>)}</tr>
                  <tr className="border-t"><td>SNR (provisional)</td><td>{c.baseline.snr?.toFixed(1) ?? 'n/a'}</td>{c.experiments.map(e => <td key={e.label}>{e.snr?.toFixed(1) ?? 'n/a'}</td>)}</tr>
                  <tr className="border-t"><td>Top reference (status)</td><td>{c.baseline.top1}</td>{c.experiments.map(e => <td key={e.label}>{e.top1} ({e.status}){e.same_top1_as_baseline ? '' : ' ≠ baseline'}</td>)}</tr>
                </tbody></table>
              <p className="mt-1 text-xs text-slate-600">Peak-height ratios are baseline-corrected counts, comparable only if acquisition settings match.</p>
            </section>
          </div>
          {c.experiments.map(e => e.warnings.length > 0 && <Notes key={e.label} title={`Warnings: ${e.label}`} items={e.warnings} />)}
          <Plain r={c} /><Insights items={c.insights} />
          <AddToReport study={{ kind: 'conditions', title: 'Experimental conditions comparison', result: c }} onAdd={onAdd} />
        </>
      )}
    </div>
  )
}
