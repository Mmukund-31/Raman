import { BASE, handle } from './api'
import type { Benchmark, Conditions, ExcitationInfo, Matrix, PcaResult, Study, Sweep, Translation } from '../types/research'

const post = <T,>(path: string, body: unknown) =>
  fetch(`${BASE}${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
    .then(r => handle<T>(r))

export interface SpectrumRef { example_id?: string; reference_id?: string; csv_text?: string; excitation_nm?: number }
export interface Step { kind: string; params: Record<string, number> }
export interface ExperimentIn {
  label: string; data_class: string; metadata: Record<string, string | number>; spectrum?: SpectrumRef; simulate?: Step[]; seed?: number
}

export const compareConditions = (baseline: ExperimentIn, experiments: ExperimentIn[]) =>
  post<Conditions>('/api/conditions/compare', { baseline, experiments })
export const excitationInfo = (nm: number) =>
  fetch(`${BASE}/api/conditions/excitation-info?excitation_nm=${nm}`).then(r => handle<ExcitationInfo>(r))
export const runSweep = (body: { spectrum: SpectrumRef; kind: string; levels?: number[]; fixed_params?: Record<string, number>; with_model: boolean }) =>
  post<Sweep>('/api/sensitivity/sweep', body)
export const runMatrix = (spectrum: SpectrumRef) => post<Matrix>('/api/sensitivity/matrix', { spectrum })
export const runPca = (body: Record<string, unknown>) => post<PcaResult>('/api/pca/run', body)
export const runBenchmark = (body: Record<string, unknown>) => post<Benchmark>('/api/benchmark/run', body)
export const runTranslation = (body: Record<string, unknown>) => post<Translation>('/api/translation/evaluate', body)

export async function researchReportHtml(studies: Study[]): Promise<string> {
  const r = await fetch(`${BASE}/api/report/research`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(studies),
  })
  if (!r.ok) throw new Error('Could not generate the research report')
  return r.text()
}
