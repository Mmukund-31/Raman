import { useEffect, useState } from 'react'
import { Results } from '../components/Results'
import { SpectrumPlot } from '../components/SpectrumPlot'
import { analyzeExample, analyzeFile, getExamples } from '../services/api'
import { defaultOptions, type Example, type Options, type Result } from '../types'

export function Analyze() {
  const [examples, setExamples] = useState<Example[]>([])
  const [opts, setOpts] = useState<Options>(defaultOptions)
  const [excitation, setExcitation] = useState('532')
  const [file, setFile] = useState<File | null>(null)
  const [example, setExample] = useState('')
  const [result, setResult] = useState<Result | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => { getExamples().then(setExamples).catch(e => setError(`Cannot reach API: ${e.message}`)) }, [])

  const run = async () => {
    setBusy(true); setError('')
    try {
      if (file) setResult(await analyzeFile(file, opts, excitation))
      else if (example) setResult(await analyzeExample(example, opts))
      else setError('Choose an example spectrum or upload a CSV file first.')
    } catch (e) { setError((e as Error).message); setResult(null) }
    setBusy(false)
  }
  const set = <K extends keyof Options>(k: K, v: Options[K]) => setOpts(o => ({ ...o, [k]: v }))
  const field = 'rounded border border-slate-300 px-2 py-1'

  return (
    <div className="space-y-6">
      <section className="rounded bg-white p-4 shadow-sm">
        <h2 className="mb-1 text-xl font-semibold">1. Choose a spectrum</h2>
        <p className="mb-3 text-sm text-slate-600">
          CSV with columns <code>raman_shift_cm1</code> (or <code>wavelength_nm</code> + excitation wavelength) and <code>intensity</code>; at least 50 rows; max 5 MB.
        </p>
        <div className="grid gap-3 md:grid-cols-3">
          <label className="text-sm">Bundled example
            <select className={`${field} w-full`} value={example} onChange={e => { setExample(e.target.value); setFile(null) }}>
              <option value="">— none —</option>
              {examples.map(x => <option key={x.sample_id} value={x.sample_id}>{x.sample_id} [{x.category}]</option>)}
            </select>
          </label>
          <label className="text-sm">…or upload CSV
            <input type="file" accept=".csv,text/csv" className={`${field} w-full`} onChange={e => { setFile(e.target.files?.[0] ?? null); if (e.target.files?.[0]) setExample('') }} />
          </label>
          <label className="text-sm">Excitation wavelength (nm)
            <input className={`${field} w-full`} inputMode="decimal" value={excitation} onChange={e => setExcitation(e.target.value)} />
          </label>
        </div>
        {example && <p className="mt-2 text-xs text-slate-600">{examples.find(x => x.sample_id === example)?.description}. <b>Synthetic data — not a physical measurement.</b></p>}
      </section>

      <section className="rounded bg-white p-4 shadow-sm">
        <h2 className="mb-2 text-xl font-semibold">2. Processing</h2>
        <div className="grid gap-3 text-sm sm:grid-cols-2 md:grid-cols-4">
          <label><input type="checkbox" checked={opts.baseline} onChange={e => set('baseline', e.target.checked)} /> ALS baseline correction</label>
          <label><input type="checkbox" checked={opts.smooth} onChange={e => set('smooth', e.target.checked)} /> Savitzky–Golay smoothing</label>
          <label>Window (odd)
            <input type="number" min={3} max={101} className={`${field} w-full`} value={opts.window} disabled={!opts.smooth} onChange={e => set('window', Number(e.target.value))} />
          </label>
          <label>Polynomial order
            <input type="number" min={1} max={7} className={`${field} w-full`} value={opts.poly} disabled={!opts.smooth} onChange={e => set('poly', Number(e.target.value))} />
          </label>
          <label>Normalization
            <select className={`${field} w-full`} value={opts.normalize} onChange={e => set('normalize', e.target.value as Options['normalize'])}>
              <option value="vector">Vector (L2)</option><option value="max">Max intensity</option><option value="none">None</option>
            </select>
          </label>
          <label>Peak prominence (fraction)
            <input type="number" step={0.01} min={0.01} max={0.9} className={`${field} w-full`} value={opts.prominence} onChange={e => set('prominence', Number(e.target.value))} />
          </label>
        </div>
        <button onClick={run} disabled={busy} className="mt-4 rounded bg-blue-700 px-5 py-2 font-medium text-white hover:bg-blue-800 disabled:opacity-50">
          {busy ? 'Analyzing…' : 'Analyze spectrum'}
        </button>
        {error && <p role="alert" className="mt-3 rounded border border-red-600 bg-red-50 p-2 text-sm text-red-800">Error: {error}</p>}
      </section>

      {result && (
        <>
          <section className="grid gap-4 rounded bg-white p-4 shadow-sm lg:grid-cols-2">
            <SpectrumPlot r={result} kind="raw" />
            <SpectrumPlot r={result} kind="processed" />
          </section>
          <Results r={result} />
        </>
      )}
    </div>
  )
}
