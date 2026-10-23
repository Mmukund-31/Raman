import { useState } from 'react'
import { field } from '../components/theme'
import { AddToReport, Busy, DataBadge, Insights, Notes, Plain } from '../components/Research'
import { runBenchmark } from '../services/research'
import type { Benchmark, Study } from '../types/research'

const kb = (b?: number) => (b == null ? '—' : b > 1e6 ? `${(b / 1e6).toFixed(1)} MB` : `${(b / 1e3).toFixed(0)} kB`)

export function ModelBenchmark({ onAdd }: { onAdd: (s: Study) => void }) {
  const [nSpec, setNSpec] = useState(24)
  const [deep, setDeep] = useState(false)
  const [res, setRes] = useState<Benchmark | null>(null)
  const [sel, setSel] = useState('pca_svm')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const run = async () => {
    setBusy(true); setError('')
    try { setRes(await runBenchmark({ n_specimens: nSpec, include_deep: deep, deep_epochs: 30 })) } catch (e) { setError((e as Error).message); setRes(null) }
    setBusy(false)
  }
  const ran = res?.models.filter(m => m.status === 'ran') ?? []
  const rep = res?.models.find(m => m.model === sel)?.clean_report

  return (
    <div className="space-y-6">
      <section className="rounded bg-white p-4 shadow-sm">
        <h2 className="text-xl font-semibold">Model Benchmark</h2>
        <p className="mb-3 text-sm text-slate-700">
          Compares reference matching, PCA + SVM, PCA + logistic regression and (optionally) a 1-D CNN and a ResNet-18 adapted to 1-D spectra, on identical specimen-level splits.
          Because the only available data are <b>simulated from a synthetic library</b>, these numbers show that the evaluation protocol works. They are <b>not</b> real-world accuracy, and this is not a reproduction of the arXiv:2601.16107 benchmark.
        </p>
        <div className="flex flex-wrap items-end gap-4 text-sm">
          <label>Specimens per material<input type="number" min={6} max={60} className={field} value={nSpec} onChange={e => setNSpec(Number(e.target.value))} /></label>
          <label><input type="checkbox" checked={deep} onChange={e => setDeep(e.target.checked)} /> Include deep models (slower; needs PyTorch)</label>
          <button onClick={run} disabled={busy} className="rounded bg-blue-700 px-5 py-2 font-medium text-white hover:bg-blue-800 disabled:opacity-50">Run benchmark</button>
        </div>
        <Busy busy={busy} error={error} />
      </section>

      {res && (
        <>
          <Notes items={[res.warning, res.reference_framework]} />
          <section className="overflow-auto rounded bg-white p-4 text-sm shadow-sm">
            <h3 className="font-semibold">Accuracy / macro-F1 by scenario <DataBadge dc={res.data_class} /></h3>
            <table className="w-full"><thead><tr className="text-left"><th>Model</th>{res.scenarios.map(s => <th key={s}>{s}</th>)}</tr></thead>
              <tbody>{ran.map(m => (
                <tr key={m.model} className="border-t"><td>{m.model}</td>{res.scenarios.map(s => <td key={s}>{m.by_scenario![s].accuracy.toFixed(2)} / {m.by_scenario![s].macro_f1.toFixed(2)}</td>)}</tr>))}</tbody></table>
            <p className="mt-1 text-xs text-slate-600">Scenarios perturb the test spectra only; training data are nominal. {res.out_of_distribution.detector} flagged:
              {' '}{Object.entries(res.out_of_distribution.flagged_fraction_by_scenario).map(([k, v]) => `${k} ${(100 * v).toFixed(0)}%`).join(', ')}.</p>
          </section>
          <section className="overflow-auto rounded bg-white p-4 text-sm shadow-sm">
            <h3 className="font-semibold">Cost and status</h3>
            <table className="w-full"><thead><tr className="text-left"><th>Model</th><th>Status</th><th>Train (s)</th><th>Inference (ms/spectrum)</th><th>Size</th><th>Hyper-parameters / note</th></tr></thead>
              <tbody>{res.models.map(m => (
                <tr key={m.model} className="border-t"><td>{m.model}</td><td>{m.status}</td><td>{m.train_seconds?.toFixed(2) ?? '—'}</td><td>{m.inference_ms_per_spectrum?.toFixed(2) ?? '—'}</td><td>{kb(m.model_size_bytes)}</td>
                  <td>{m.reason ?? `${JSON.stringify(m.hyperparameters)} ${m.note ?? ''}`}</td></tr>))}</tbody></table>
          </section>
          <section className="rounded bg-white p-4 text-sm shadow-sm">
            <label>Detailed report for <select className="rounded border border-slate-300 px-2 py-1" value={sel} onChange={e => setSel(e.target.value)}>{ran.map(m => <option key={m.model}>{m.model}</option>)}</select> on clean test data</label>
            {rep && (
              <div className="mt-2 grid gap-4 md:grid-cols-2">
                <div>
                  <p>Accuracy {rep.accuracy.toFixed(3)} · macro-F1 {rep.macro_f1.toFixed(3)} · n = {rep.n}{rep.expected_calibration_error != null && ` · calibration error (ECE) ${rep.expected_calibration_error.toFixed(3)}`}</p>
                  <table className="mt-1 w-full"><thead><tr className="text-left"><th>Class</th><th>Precision</th><th>Recall</th><th>Support</th></tr></thead>
                    <tbody>{rep.per_class.map(c => <tr key={c.label} className="border-t"><td>{c.label}</td><td>{c.precision.toFixed(2)}</td><td>{c.recall.toFixed(2)}</td><td>{c.support}</td></tr>)}</tbody></table>
                </div>
                <div>
                  <p className="font-medium">Confusion matrix (rows = true, columns = predicted)</p>
                  <table className="mt-1 text-center"><thead><tr><th></th>{rep.labels.map(l => <th key={l} className="px-1 text-xs">{l.slice(0, 6)}</th>)}</tr></thead>
                    <tbody>{rep.confusion_matrix.map((r, i) => <tr key={i}><th className="pr-2 text-left text-xs">{rep.labels[i].slice(0, 6)}</th>{r.map((v, j) => <td key={j} className={`px-2 ${i === j ? 'bg-emerald-100' : v ? 'bg-red-100' : ''}`}>{v}</td>)}</tr>)}</tbody></table>
                </div>
              </div>)}
          </section>
          <section className="rounded bg-white p-4 text-xs text-slate-700 shadow-sm">
            <h3 className="text-sm font-semibold">Protocol and record</h3>
            <ul className="list-disc pl-5">{res.protocol.map(p => <li key={p}>{p}</li>)}
              <li>Splits: {Object.entries(res.splits).map(([k, v]) => `${k} = ${v}`).join('; ')}</li>
              <li>Class counts: {JSON.stringify(res.class_counts)} (imbalance ratio {res.imbalance_ratio.toFixed(2)}); missing labels 0</li>
              <li>Environment: {JSON.stringify(res.environment)}; seed {String(res.config.seed)}</li></ul>
          </section>
          <Plain r={res} /><Insights items={res.insights} />
          <AddToReport study={{ kind: 'benchmark', title: 'Model benchmark (simulated data)', result: res }} onAdd={onAdd} />
        </>
      )}
    </div>
  )
}
