import { BASE } from './api'
import type { AnalysisInput, Conditions, FullReport, ProgressEvent } from '../types/report'

export class AnalysisError extends Error {
  stage?: string
  constructor(message: string, stage?: string) { super(message); this.stage = stage }
}

/** Splits a text stream into newline-delimited JSON events; tolerates chunks that cut a line in half. */
export function ndjsonParser(onEvent: (e: ProgressEvent) => void) {
  let buf = ''
  const emit = (line: string) => { if (line.trim()) onEvent(JSON.parse(line) as ProgressEvent) }
  return {
    push(chunk: string) {
      buf += chunk
      let i
      while ((i = buf.indexOf('\n')) >= 0) { emit(buf.slice(0, i)); buf = buf.slice(i + 1) }
    },
    end() { emit(buf); buf = '' },
  }
}

/** Only fields the user filled in are sent; blank means "not recorded", never zero. */
export function conditionsToMetadata(c: Conditions): Record<string, string | number> {
  const m: Record<string, string | number> = {}
  const num = (k: keyof Conditions, out: string = k) => { if (c[k].trim()) m[out] = Number(c[k]) }
  if (c.temperature.trim()) { num('temperature'); m.temperature_unit = c.temperature_unit }
  if (c.laser_power.trim()) { num('laser_power'); m.laser_power_unit = c.laser_power_unit }
  num('exposure_s'); num('incidence_angle_deg'); num('collection_angle_deg'); num('spot_diameter_um')
  if (c.geometry.trim()) m.geometry = c.geometry.trim()
  if (c.instrument.trim()) m.instrument = c.instrument.trim()
  for (const [k, v] of Object.entries(m)) if (typeof v === 'number' && !Number.isFinite(v)) throw new AnalysisError(`'${k.replace(/_/g, ' ')}' must be a number.`, 'validate')
  return m
}

export function buildRequest(input: AnalysisInput): { url: string; init: RequestInit } {
  const metadata = conditionsToMetadata(input.conditions)
  if (input.file) {
    const f = new FormData()
    f.append('file', input.file)
    f.append('sample_id', input.file.name.replace(/\.csv$/i, ''))
    if (input.excitation.trim()) f.append('excitation_nm', input.excitation.trim())
    f.append('origin', input.origin)
    f.append('metadata', JSON.stringify(metadata))
    f.append('primary_label', input.primaryLabel)
    input.extras.forEach(e => f.append('extra_files', e.file))
    f.append('extra_labels', JSON.stringify(input.extras.map(e => e.label)))
    f.append('stream', 'true')
    for (const [k, v] of Object.entries(input.options)) f.append(k, String(v))
    return { url: `${BASE}/api/full-report`, init: { method: 'POST', body: f } }
  }
  if (input.example) {
    return {
      url: `${BASE}/api/full-report/example/${encodeURIComponent(input.example)}?stream=true`,
      init: { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ options: input.options, metadata }) },
    }
  }
  throw new AnalysisError('Choose a CSV file or a bundled example first.', 'validate')
}

async function errorMessage(r: Response) {
  try {
    const j = await r.json()
    return typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)
  } catch { return `The server returned an error (${r.status}).` }
}

/** Runs the whole analysis, reporting each stage as the server actually starts and finishes it. */
export async function runAnalysis(input: AnalysisInput, onEvent: (e: ProgressEvent) => void, signal?: AbortSignal): Promise<FullReport> {
  const { url, init } = buildRequest(input)
  let r: Response
  try { r = await fetch(url, { ...init, signal }) } catch (e) {
    if ((e as Error).name === 'AbortError') throw e
    throw new AnalysisError('Cannot reach the analysis server. Check that the backend is running, then try again.')
  }
  if (!r.ok) throw new AnalysisError(await errorMessage(r), 'validate')
  if (!r.body) throw new AnalysisError('The server response could not be read.')
  const out: { report?: FullReport; failure?: AnalysisError } = {}
  const parser = ndjsonParser(e => {
    if (e.event === 'result') out.report = e.report
    else if (e.event === 'error') out.failure = new AnalysisError(e.message, e.stage)
    onEvent(e)
  })
  const reader = r.body.getReader()
  const decoder = new TextDecoder()
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    parser.push(decoder.decode(value, { stream: true }))
  }
  parser.end()
  if (out.failure) throw out.failure
  if (!out.report) throw new AnalysisError('The connection closed before the report was finished. Please try again.')
  return out.report
}

export async function fetchFullReportHtml(report: FullReport): Promise<string> {
  const r = await fetch(`${BASE}/api/full-report/html`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(report),
  })
  if (!r.ok) throw new Error(await errorMessage(r))
  return r.text()
}

export function download(name: string, text: string, type: string) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([text], { type }))
  a.download = name
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 0)
}

/** Prints the server-rendered report from a hidden frame; the browser's "Save as PDF" produces the PDF. */
export function printHtml(html: string) {
  const frame = document.createElement('iframe')
  frame.setAttribute('aria-hidden', 'true')
  frame.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0'
  frame.srcdoc = html
  frame.onload = () => {
    const w = frame.contentWindow
    if (!w) return
    w.addEventListener('afterprint', () => setTimeout(() => frame.remove(), 0))
    w.focus()
    w.print()
  }
  document.body.appendChild(frame)
}

export const processedCsv = (r: FullReport) => {
  const d = r.sections.spectrum.data
  return 'raman_shift_cm1,raw,baseline,processed\n' + d.x.map((x, i) => `${x},${d.raw[i]},${d.baseline[i]},${d.processed[i]}`).join('\n')
}

