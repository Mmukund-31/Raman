import { useEffect, useRef, useState, type DragEvent } from 'react'
import { AnalysisLoader } from '../components/AnalysisLoader'
import { ResearchReport } from '../components/report/ResearchReport'
import { exampleDownloadUrl, getExamples, getTestFiles, testFilesZipUrl, testFileUrl } from '../services/api'
import { applyEvent, failRunning, INITIAL_STAGES, isFinished, paced, STEP_MS, type StageState } from '../services/progress'
import { runAnalysis } from '../services/report'
import { defaultOptions, type Example, type TestFile } from '../types'
import { emptyConditions, type FullReport } from '../types/report'

type Phase = 'upload' | 'running' | 'error' | 'done'
type Source = { file: File } | { example: Example }

const NEEDS_EXCITATION = /excitation wavelength/i
const ACCEPT = '.csv,.tsv,.txt,.dat,.jdx,.dx,.jcamp,.rod,.cif,.json,text/csv,text/plain,application/json'

function expectation(t: TestFile) {
  const e = t.expected
  if (e.expect === 'match') return { text: `Expected: ${e.material?.replace(/_/g, ' ')}`, tone: 'text-emerald-700 bg-emerald-50' }
  if (e.expect === 'inconclusive') return { text: 'Expected: inconclusive', tone: 'text-amber-700 bg-amber-50' }
  if (e.expect === 'error') return { text: 'Expected: clear error', tone: 'text-rose-700 bg-rose-50' }
  return { text: `Expected: ${(e.allowed ?? []).join(' or ')}`, tone: 'text-slate-600 bg-slate-100' }
}

function TestFiles({ files, onRun }: { files: TestFile[]; onRun: (f: File, excitation: string) => void }) {
  const [busy, setBusy] = useState('')
  const analyze = async (t: TestFile) => {
    setBusy(t.id)
    try {
      const blob = await (await fetch(testFileUrl(t.id))).blob()
      onRun(new File([blob], t.file), t.excitation_nm ? String(t.excitation_nm) : '')
    } finally { setBusy('') }
  }
  return (
    <details className="mt-8 rounded-2xl border border-slate-200 bg-white">
      <summary className="cursor-pointer px-5 py-4 text-sm font-medium text-slate-800">
        Test files ({files.length}) <span className="font-normal text-slate-500">· real and synthetic spectra in many formats, each with its expected result</span>
      </summary>
      <div className="border-t border-slate-200 px-5 py-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
          <span>Real spectra come from RRUFF and the Raman Open Database, from specimens that are not in the reference library.</span>
          <a className="btn-ghost" href={testFilesZipUrl()} download>Download all (zip)</a>
        </div>
        <ul className="divide-y divide-slate-100">
          {files.map(t => {
            const ex = expectation(t)
            return (
              <li key={t.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-2.5 text-sm">
                <span className="min-w-0 flex-1">
                  <span className="font-mono text-[13px] text-slate-900">{t.file}</span>
                  <span className="block text-xs text-slate-500">{t.description}</span>
                </span>
                <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${ex.tone}`}>{ex.text}</span>
                <a className="text-accent-600 hover:underline" href={testFileUrl(t.id)} download={t.file}>Download</a>
                <button type="button" className="text-accent-600 hover:underline disabled:opacity-50" disabled={!!busy} onClick={() => analyze(t)}>
                  {busy === t.id ? 'Loading…' : 'Analyze'}
                </button>
              </li>
            )
          })}
        </ul>
      </div>
    </details>
  )
}

function UploadPanel({ onFile }: { onFile: (f: File) => void }) {
  const [over, setOver] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const drop = (e: DragEvent) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files?.[0]; if (f) onFile(f) }
  return (
    <div onDragOver={e => { e.preventDefault(); setOver(true) }} onDragLeave={() => setOver(false)} onDrop={drop}
      className={`group relative rounded-3xl border bg-white p-2 shadow-[0_1px_2px_rgba(15,23,42,0.04),0_12px_40px_-12px_rgba(31,69,184,0.18)] transition ${over ? 'border-accent-500 ring-4 ring-accent-100' : 'border-slate-200'}`}>
      <button type="button" onClick={() => input.current?.click()}
        className={`flex w-full flex-col items-center rounded-[20px] border-2 border-dashed px-6 py-14 text-center transition sm:py-16 ${over ? 'border-accent-400 bg-accent-50/60' : 'border-slate-200 group-hover:border-accent-200 group-hover:bg-accent-50/30'}`}>
        <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-accent-600 shadow-lg shadow-accent-600/25">
          <svg aria-hidden viewBox="0 0 24 24" className="h-6 w-6 text-white"><path d="M12 16V4m0 0-4.5 4.5M12 4l4.5 4.5M4 16v2.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
        </span>
        <span className="mt-5 text-lg font-semibold text-slate-900">{over ? 'Release to analyze' : 'Upload a spectrum'}</span>
        <span className="mt-1 text-sm text-slate-500">Drop a file here, or click to browse</span>
        <span className="mt-5 max-w-md text-xs leading-relaxed text-slate-400">CSV, TSV or TXT (any delimiter, decimal commas, with or without a header), RRUFF, ROD, JCAMP-DX or JSON · up to 5 MB</span>
      </button>
      <input ref={input} type="file" accept={ACCEPT} className="sr-only" aria-label="Spectrum file"
        onChange={e => { const f = e.target.files?.[0]; e.target.value = ''; if (f) onFile(f) }} />
    </div>
  )
}

export function Analyze() {
  const [examples, setExamples] = useState<Example[]>([])
  const [testFiles, setTestFiles] = useState<TestFile[]>([])
  const [apiError, setApiError] = useState('')
  const [source, setSource] = useState<Source | null>(null)
  const [excitation, setExcitation] = useState('')
  const [phase, setPhase] = useState<Phase>('upload')
  const [server, setServer] = useState<StageState[]>(INITIAL_STAGES)
  const [revealed, setRevealed] = useState(0)
  const [pending, setPending] = useState<FullReport | null>(null)
  const [report, setReport] = useState<FullReport | null>(null)
  const [error, setError] = useState('')
  const abort = useRef<AbortController | null>(null)

  useEffect(() => { getExamples().then(setExamples).catch(() => setApiError('The analysis server is not reachable. Start the backend and reload this page.')) }, [])
  useEffect(() => { getTestFiles().then(setTestFiles).catch(() => setTestFiles([])) }, [])
  useEffect(() => () => abort.current?.abort(), [])

  // Reveal steps at a readable pace, never ahead of the server.
  const currentDone = isFinished(server[revealed])
  useEffect(() => {
    if (phase !== 'running') return
    if (revealed < server.length && currentDone) {
      const t = setTimeout(() => setRevealed(r => r + 1), STEP_MS)
      return () => clearTimeout(t)
    }
    if (revealed >= server.length && pending) {
      const t = setTimeout(() => { setReport(pending); setPhase('done'); window.scrollTo({ top: 0 }) }, 450)
      return () => clearTimeout(t)
    }
  }, [phase, revealed, currentDone, server.length, pending])

  const run = async (src: Source, exc = excitation) => {
    abort.current?.abort()
    const ctrl = new AbortController()
    abort.current = ctrl
    setSource(src); setServer(INITIAL_STAGES); setRevealed(0); setPending(null); setReport(null); setError(''); setPhase('running')
    window.scrollTo({ top: 0, behavior: 'smooth' })
    try {
      const r = await runAnalysis({
        file: 'file' in src ? src.file : null, example: 'example' in src ? src.example.sample_id : '', extras: [], primaryLabel: '',
        excitation: exc, origin: 'unknown', conditions: emptyConditions, options: defaultOptions,
      }, e => setServer(s => applyEvent(s, e)), ctrl.signal)
      setPending(r)
    } catch (e) {
      if ((e as Error).name === 'AbortError') { setPhase('upload'); return }
      setServer(failRunning); setError((e as Error).message); setPhase('error')
    }
  }
  const reset = () => { abort.current?.abort(); setPhase('upload'); setExcitation(''); window.scrollTo({ top: 0 }) }
  const name = source ? ('file' in source ? source.file.name : source.example.sample_id) : ''

  if (phase === 'done' && report) return <ResearchReport r={report} onNew={reset} />
  if (phase === 'running' || phase === 'error') {
    const needsExc = phase === 'error' && NEEDS_EXCITATION.test(error)
    return (
      <AnalysisLoader name={name} stages={phase === 'error' ? server : paced(server, revealed)} error={phase === 'error' ? error : undefined}
        onRetry={source && (!needsExc || excitation.trim()) ? () => run(source) : undefined} onBack={reset} onCancel={reset}>
        {needsExc && (
          <label className="mt-4 block text-sm">
            <span className="font-medium text-slate-700">This file uses wavelengths. Enter the laser excitation wavelength to convert it:</span>
            <input className="field mt-2 max-w-48" inputMode="decimal" placeholder="e.g. 785 nm" autoFocus value={excitation} onChange={e => setExcitation(e.target.value)} />
          </label>
        )}
      </AnalysisLoader>
    )
  }

  return (
    <div className="mx-auto max-w-3xl">
      <div className="pt-6 pb-10 text-center sm:pt-12">
        <p className="inline-flex items-center gap-2 rounded-full border border-accent-100 bg-accent-50 px-3 py-1 text-xs font-medium text-accent-700">
          <span className="h-1.5 w-1.5 rounded-full bg-accent-500" /> Automated Raman analysis
        </p>
        <h1 className="mt-5 text-4xl font-semibold tracking-tight text-balance text-slate-900 sm:text-5xl">From spectrum to research report in seconds</h1>
        <p className="mx-auto mt-4 max-w-xl text-lg leading-relaxed text-pretty text-slate-500">
          Upload one file. RamanReach processes the spectrum, identifies peaks, compares it with reference spectra, tests robustness and writes the report.
        </p>
      </div>

      {apiError && <p role="alert" className="mb-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-900">{apiError}</p>}
      <UploadPanel onFile={f => run({ file: f }, '')} />

      {examples.length > 0 && (
        <p className="mt-6 text-center text-sm text-slate-500">
          No file at hand? Try a sample:{' '}
          {examples.map((x, i) => (
            <span key={x.sample_id}>
              {i > 0 && <span className="text-slate-300"> · </span>}
              <button type="button" title={`${x.description} (synthetic)`} onClick={() => run({ example: x }, '')} className="font-medium text-accent-600 hover:text-accent-700 hover:underline">
                {x.sample_id.replace('demo_', '').replace('_synthetic', '').replace(/_/g, ' ')}
              </button>
              <a href={exampleDownloadUrl(x.sample_id)} download aria-label={`Download ${x.sample_id}`} title="Download this CSV" className="ml-1 text-slate-400 hover:text-accent-600">↓</a>
            </span>
          ))}
        </p>
      )}

      {testFiles.length > 0 && <TestFiles files={testFiles} onRun={(f, exc) => { setExcitation(exc); run({ file: f }, exc) }} />}

      <ol className="mt-16 grid gap-6 border-t border-slate-200 pt-10 sm:grid-cols-3">
        {[['Upload', 'One spectrum file in any common export format. No settings to fill in.'], ['Automated analysis', 'Processing, peak detection, reference comparison and robustness tests.'],
          ['One clear report', 'A plain-language answer first, with the figures, tables and evidence behind it.']].map(([t, d], i) => (
          <li key={t}>
            <p className="text-xs font-semibold text-accent-600 tabular-nums">0{i + 1}</p>
            <p className="mt-1 font-medium text-slate-900">{t}</p>
            <p className="mt-1 text-sm leading-relaxed text-slate-500">{d}</p>
          </li>
        ))}
      </ol>
    </div>
  )
}
