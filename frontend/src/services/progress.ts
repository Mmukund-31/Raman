import type { ProgressEvent, StageStatus } from '../types/report'

export interface StageState { id: string; label: string; status: StageStatus; detail?: string | null }

/** Mirrors backend orchestrator.STAGES so the list is visible before the first event; server labels replace these. */
export const INITIAL_STAGES: StageState[] = [
  ['validate', 'Reading and validating the file'],
  ['process', 'Processing spectrum, detecting peaks and matching references'],
  ['conditions', 'Reviewing experimental conditions'],
  ['sensitivity', 'Running wavenumber sensitivity tests'],
  ['pca', 'Comparing spectra with PCA'],
  ['models', 'Checking model benchmark and translation requirements'],
  ['report', 'Assembling the final report'],
  ['explain', 'Writing the plain-language summary'],
].map(([id, label]) => ({ id, label, status: 'pending' as const }))

/** Applies one server event. A stage only changes state when the server says so; nothing is advanced on a timer. */
export function applyEvent(stages: StageState[], e: ProgressEvent): StageState[] {
  if (e.event === 'stage') {
    const next = { id: e.stage, label: e.label, status: e.status, detail: e.detail }
    return stages.some(s => s.id === e.stage) ? stages.map(s => (s.id === e.stage ? next : s)) : [...stages, next]
  }
  if (e.event === 'error') return stages.map(s => (s.id === e.stage || s.status === 'running' ? { ...s, status: 'error' } : s))
  return stages
}

/** Minimum time each step stays on screen, so 7 steps take about 5 s even when the server is faster. */
export const STEP_MS = 700

/**
 * What the user sees: the server's real state, revealed one step at a time. The display may lag the server but never
 * leads it: a step is shown finished only once the server has finished it, and shown running only once it has started.
 */
export function paced(server: StageState[], revealed: number): StageState[] {
  return server.map((s, i) => {
    if (i < revealed) return s
    if (i === revealed && s.status !== 'pending') return { ...s, status: 'running' }
    return { ...s, status: 'pending' }
  })
}

export const isFinished = (s?: StageState) => !!s && (s.status === 'done' || s.status === 'skipped' || s.status === 'error')

/** On a failure outside the stream (network, abort), mark whichever stage was running as failed. */
export const failRunning = (stages: StageState[]): StageState[] => stages.map(s => (s.status === 'running' ? { ...s, status: 'error' } : s))
