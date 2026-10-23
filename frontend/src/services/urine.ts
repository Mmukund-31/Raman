import { BASE, handle } from './api'
import type { UrineDataset, UrineDatasetId, UrineExample, UrineParticipant, UrineResult, UrineStudy } from '../types/urine'

export const getUrineDatasets = () => fetch(`${BASE}/api/urine/datasets`).then(r => handle<UrineDataset[]>(r))
export const getUrineStudy = (d: UrineDatasetId) => fetch(`${BASE}/api/urine/study/${d}`).then(r => handle<UrineStudy>(r))
export const getParticipant = (pid: string) => fetch(`${BASE}/api/urine/participant/${encodeURIComponent(pid)}`).then(r => handle<UrineParticipant>(r))
export const getUrineExamples = () => fetch(`${BASE}/api/urine/examples`).then(r => handle<UrineExample[]>(r))
export const urineExampleUrl = (id: string) => `${BASE}/api/urine/examples/${encodeURIComponent(id)}/download`

export function analyzeUrine(dataset: UrineDatasetId, src: { file: File } | { example: string }) {
  const f = new FormData()
  f.append('dataset', dataset)
  if ('file' in src) f.append('file', src.file)
  else f.append('example', src.example)
  return fetch(`${BASE}/api/urine/analyze`, { method: 'POST', body: f }).then(r => handle<UrineResult>(r))
}
