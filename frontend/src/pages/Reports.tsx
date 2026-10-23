import { useState } from 'react'
import { DataBadge } from '../components/Research'
import { researchReportHtml } from '../services/research'
import type { Study } from '../types/research'
import { RamanBasics } from '../components/RamanBasics'
import { About } from './Info'

const SECTIONS: [keyof Study['result']['report'], string][] = [
  ['tested', 'A. What did we test?'], ['changed', 'B. What changed?'], ['graph', 'C. What does the graph show?'], ['pca', 'D. What did PCA reveal?'],
  ['model', 'E. How did the model perform?'], ['trust', 'F. Can we trust this result?'], ['conclusion', 'G. What should the user conclude?'],
]

export function Reports({ studies, remove }: { studies: Study[]; remove: (i: number) => void }) {
  const [err, setErr] = useState('')
  const download = async () => {
    try {
      setErr('')
      const html = await researchReportHtml(studies)
      const a = document.createElement('a')
      a.href = URL.createObjectURL(new Blob([html], { type: 'text/html' }))
      a.download = 'ramanreach-research-report.html'
      a.click()
      URL.revokeObjectURL(a.href)
    } catch (e) { setErr((e as Error).message) }
  }
  return (
    <div className="space-y-6">
      <section className="rounded bg-white p-4 shadow-sm">
        <h2 className="text-xl font-semibold">Reports</h2>
        <p className="text-sm text-slate-700">Use “Add to report” in any lab to collect its results here. The report explains each study in plain language (sections A–G) and lists the evidence, validation status and limits behind every statement.</p>
        {studies.length === 0 ? <p className="mt-2 text-sm">No studies collected yet.</p> : (
          <>
            <button onClick={download} className="mt-3 rounded bg-blue-700 px-5 py-2 font-medium text-white hover:bg-blue-800">Download HTML report ({studies.length})</button>
            {err && <p role="alert" className="mt-2 text-sm text-red-800">Error: {err}</p>}
            <div className="mt-4 space-y-4">
              {studies.map((s, i) => (
                <article key={i} className="rounded border border-slate-200 p-3 text-sm">
                  <h3 className="font-semibold">{s.title} <DataBadge dc={s.result.data_class} /> <button className="ml-2 text-xs text-red-700 underline" onClick={() => remove(i)}>remove</button></h3>
                  {SECTIONS.map(([k, t]) => <p key={k} className="mt-1"><b>{t}</b> {s.result.report[k]}</p>)}
                </article>))}
            </div>
          </>)}
      </section>
      <section className="rounded bg-white p-4 text-sm shadow-sm">
        <h2 className="mb-2 text-xl font-semibold">Methodology of the research labs</h2>
        <ul className="list-disc space-y-1 pl-5">
          <li><b>Perturbations</b> are simulated and labelled by class: axis calibration, physical, instrumental or processing. A global axis shift and a global physical peak shift can look identical in the reported coordinates.</li>
          <li><b>Sweeps</b> re-run the unchanged analysis pipeline at increasing perturbation size and report where the provisional quality gate stops giving a confirmed correct answer. Levels are configurable test ranges, not instrument tolerances.</li>
          <li><b>PCA</b> uses identical preprocessing for every spectrum, a documented scaling, and reports explained variance, loadings and how strongly material and condition are associated with each component.</li>
          <li><b>Benchmark</b> splits by specimen, tunes on training data only, and compares models on identical test spectra plus distribution-shift scenarios. Deep models are optional.</li>
          <li><b>Translation</b> estimates parameters from a separate calibration standard and is judged on fidelity metrics <i>and</i> peak preservation <i>and</i> downstream classification, each against resampling alone.</li>
          <li><b>Insights</b> are rule-generated from computed metrics and labelled observed, supported, hypothesis or inconclusive. Self-checks compare the pipeline with injected ground truth.</li>
          <li><b>Not established:</b> real-instrument tolerances, material-specific temperature, excitation or geometry effects, or any real-world accuracy. All bundled data are synthetic.</li>
        </ul>
      </section>
      <RamanBasics />
      <About />
    </div>
  )
}
