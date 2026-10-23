import { useState } from 'react'
import type { Data } from 'plotly.js'
import { PALETTE, field } from '../components/theme'
import { AddToReport, Busy, Chart, Checks, Insights, Notes, Plain } from '../components/Research'
import { runPca } from '../services/research'
import type { PcaResult, Study } from '../types/research'

const CONDS: Record<string, { name: string; steps: { kind: string; params: Record<string, number> }[] }> = {
  shift: { name: 'axis shift +6 cm⁻¹', steps: [{ kind: 'axis_shift', params: { delta_cm1: 6 } }] },
  fluor: { name: 'strong baseline (1.5x)', steps: [{ kind: 'baseline_distortion', params: { amplitude_frac: 1.5 } }] },
  broad: { name: 'broadening 8 cm⁻¹', steps: [{ kind: 'broadening', params: { sigma_cm1: 8 } }] },
  noisy: { name: 'noise 10% of range', steps: [{ kind: 'noise', params: { sigma_frac: 0.1 } }] },
}

export function PcaExplorer({ onAdd }: { onAdd: (s: Study) => void }) {
  const [nSpec, setNSpec] = useState(8)
  const [nComp, setNComp] = useState(5)
  const [scaling, setScaling] = useState('none')
  const [on, setOn] = useState<string[]>(['shift'])
  const [baseline, setBaseline] = useState(true)
  const [smooth, setSmooth] = useState(true)
  const [normalize, setNormalize] = useState('vector')
  const [res, setRes] = useState<PcaResult | null>(null)
  const [colorBy, setColorBy] = useState<'material' | 'condition'>('material')
  const [px, setPx] = useState(0)
  const [py, setPy] = useState(1)
  const [lpc, setLpc] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const run = async () => {
    setBusy(true); setError('')
    try {
      const conditions = [{ name: 'nominal', steps: [] }, ...on.map(k => CONDS[k])]
      const r = await runPca({ n_specimens: nSpec, n_repeats: 2, conditions, n_components: nComp, scaling, options: { baseline, smooth, normalize } })
      setRes(r); setPx(0); setPy(1); setLpc(0)
    } catch (e) { setError((e as Error).message); setRes(null) }
    setBusy(false)
  }

  const groups = res ? [...new Set(res.scores.map(s => s[colorBy]))] : []
  const scatter: Data[] = res ? groups.map((g, i) => {
    const pts = res.scores.filter(s => s[colorBy] === g)
    return { x: pts.map(p => p.scores[px]), y: pts.map(p => p.scores[py]), type: 'scatter', mode: 'markers', name: g, marker: { color: PALETTE[i % PALETTE.length], size: 8 },
      text: pts.map(p => `${p.spectrum_id}<br>specimen ${p.specimen_id}<br>material ${p.material}<br>condition ${p.condition}`), hoverinfo: 'text' } as Data
  }) : []
  const pct = (k: number) => res ? `${(100 * res.explained_variance_ratio[k]).toFixed(1)}%` : ''
  const scree: Data[] = res ? [{ x: res.explained_variance_ratio.map((_, i) => `PC${i + 1}`), y: res.explained_variance_ratio.map(v => 100 * v), type: 'bar', marker: { color: '#0072B2' }, name: 'explained variance' }] : []
  const load: Data[] = res ? [{ x: res.grid, y: res.loadings[lpc].values, type: 'scatter', mode: 'lines', name: `PC${lpc + 1} loading`, line: { color: '#D55E00' } }] : []
  const cond = res ? `${res.n_spectra} simulated spectra; preprocessing: ${baseline ? 'ALS baseline, ' : ''}${smooth ? 'smoothing, ' : ''}${normalize} normalization; scaling: ${res.scaling}` : ''

  return (
    <div className="space-y-6">
      <section className="rounded bg-white p-4 shadow-sm">
        <h2 className="text-xl font-semibold">PCA Explorer</h2>
        <p className="mb-3 text-sm text-slate-700">
          PCA is an <b>unsupervised</b> way to see where spectra differ most. Groups in the plot do not prove that materials are chemically different, and a clean split does not guarantee a classifier will work.
          Add acquisition conditions below to check whether PCA separates by <b>material</b> or merely by <b>condition</b>. The data are simulated from the synthetic library.
        </p>
        <div className="grid gap-3 text-sm md:grid-cols-4">
          <label>Specimens per material<input type="number" min={2} max={40} className={field} value={nSpec} onChange={e => setNSpec(Number(e.target.value))} /></label>
          <label>Components<input type="number" min={2} max={10} className={field} value={nComp} onChange={e => setNComp(Number(e.target.value))} /></label>
          <label>Feature scaling<select className={field} value={scaling} onChange={e => setScaling(e.target.value)}>
            <option value="none">Mean-centre only</option><option value="pareto">Pareto</option><option value="standard">Unit variance (amplifies noise)</option></select></label>
          <label>Normalization<select className={field} value={normalize} onChange={e => setNormalize(e.target.value)}><option value="vector">Vector (L2)</option><option value="max">Max</option><option value="none">None</option></select></label>
          <label><input type="checkbox" checked={baseline} onChange={e => setBaseline(e.target.checked)} /> ALS baseline correction</label>
          <label><input type="checkbox" checked={smooth} onChange={e => setSmooth(e.target.checked)} /> Smoothing</label>
        </div>
        <fieldset className="mt-3 text-sm"><legend className="font-medium">Extra acquisition conditions (nominal is always included)</legend>
          {Object.entries(CONDS).map(([k, v]) => (
            <label key={k} className="mr-4"><input type="checkbox" checked={on.includes(k)} onChange={e => setOn(o => (e.target.checked ? [...o, k] : o.filter(x => x !== k)))} /> {v.name}</label>))}
        </fieldset>
        <button onClick={run} disabled={busy} className="mt-3 rounded bg-blue-700 px-5 py-2 font-medium text-white hover:bg-blue-800 disabled:opacity-50">Run PCA</button>
        <Busy busy={busy} error={error} />
      </section>

      {res && (
        <>
          <Notes items={[...res.warnings, res.interpretation_note]} />
          <div className="flex flex-wrap items-end gap-3 text-sm">
            <label>Colour by<select className={field} value={colorBy} onChange={e => setColorBy(e.target.value as 'material' | 'condition')}><option value="material">Material</option><option value="condition">Condition</option></select></label>
            <label>X axis<select className={field} value={px} onChange={e => setPx(Number(e.target.value))}>{res.explained_variance_ratio.map((_, i) => <option key={i} value={i}>PC{i + 1}</option>)}</select></label>
            <label>Y axis<select className={field} value={py} onChange={e => setPy(Number(e.target.value))}>{res.explained_variance_ratio.map((_, i) => <option key={i} value={i}>PC{i + 1}</option>)}</select></label>
            <label>Loadings of<select className={field} value={lpc} onChange={e => setLpc(Number(e.target.value))}>{res.loadings.map((l, i) => <option key={i} value={i}>PC{l.pc}</option>)}</select></label>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Chart traces={scatter} title="PCA scores (hover for sample ID and metadata)" xTitle={`PC${px + 1} (${pct(px)} of variance)`} yTitle={`PC${py + 1} (${pct(py)} of variance)`} dc={res.data_class} condition={cond} height={380} />
            <Chart traces={scree} title="Explained variance per component" xTitle="Principal component" yTitle="Variance explained (%)" dc={res.data_class} condition={cond} height={380} />
            <Chart traces={load} title={`PC${lpc + 1} loadings against wavenumber`} xTitle="Raman shift (cm⁻¹)" yTitle="Loading (unitless weight)" dc={res.data_class} condition={cond} />
            <section className="rounded bg-white p-4 text-sm shadow-sm">
              <h3 className="font-semibold">Spectral regions driving PC{lpc + 1}</h3>
              <ul className="list-disc pl-5">{res.loadings[lpc].top_regions.map(r => <li key={r.from}>{r.from.toFixed(0)}–{r.to.toFixed(0)} cm⁻¹ ({r.sign} weight, |loading| {r.peak_abs_loading.toFixed(3)})</li>)}</ul>
              <p className="mt-1 text-xs text-slate-600">Regions where this component's weights are largest. They show where spectra vary, not why.</p>
              <h3 className="mt-3 font-semibold">Is the structure material or condition?</h3>
              <table className="w-full"><thead><tr className="text-left"><th>Factor</th><th>Groups</th><th>Share of variance on PC1/PC2/PC3</th><th>Silhouette</th></tr></thead>
                <tbody>{res.factor_association.map(a => (
                  <tr key={a.factor} className="border-t"><td>{a.factor}</td><td>{a.n_groups}</td>
                    <td>{a.eta_squared_per_pc ? a.eta_squared_per_pc.slice(0, 3).map(v => `${(100 * v).toFixed(0)}%`).join(' / ') : a.note}</td><td>{a.silhouette?.toFixed(2) ?? '—'}</td></tr>))}</tbody></table>
              <p className="mt-1 text-xs text-slate-600">Backend: {res.ml_backend}. Association, not causation.</p>
            </section>
          </div>
          <Plain r={res} /><Insights items={res.insights} /><Checks items={res.self_checks} />
          <AddToReport study={{ kind: 'pca', title: 'PCA exploration', result: res }} onAdd={onAdd} />
        </>
      )}
    </div>
  )
}
