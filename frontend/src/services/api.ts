import type { Example, Options, Result, TestFile } from '../types'

export const BASE = import.meta.env.VITE_API_URL ?? ''

export async function handle<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let msg = `Request failed (${r.status})`
    try {
      const j = await r.json()
      msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)
    } catch { /* keep default */ }
    throw new Error(msg)
  }
  return r.json() as Promise<T>
}

export const getExamples = () => fetch(`${BASE}/api/examples`).then(r => handle<Example[]>(r))
export const getTestFiles = () => fetch(`${BASE}/api/test-files`).then(r => handle<TestFile[]>(r))
export const testFileUrl = (id: string) => `${BASE}/api/test-files/${encodeURIComponent(id)}`
export const testFilesZipUrl = () => `${BASE}/api/test-files/all.zip`
export const exampleDownloadUrl = (id: string) => `${BASE}/api/examples/${encodeURIComponent(id)}/download`

export const analyzeExample = (id: string, o: Options) =>
  fetch(`${BASE}/api/analyze/example/${id}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(o),
  }).then(r => handle<Result>(r))

export function analyzeFile(file: File, o: Options, excitation: string) {
  const f = new FormData()
  f.append('file', file)
  f.append('sample_id', file.name.replace(/\.csv$/i, ''))
  if (excitation) f.append('excitation_nm', excitation)
  for (const [k, v] of Object.entries(o)) f.append(k, String(v))
  return fetch(`${BASE}/api/analyze`, { method: 'POST', body: f }).then(r => handle<Result>(r))
}

export async function fetchReportHtml(result: Result): Promise<string> {
  const r = await fetch(`${BASE}/api/report`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(result),
  })
  if (!r.ok) throw new Error('Could not generate report')
  return r.text()
}
