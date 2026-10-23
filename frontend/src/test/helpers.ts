import type { FullReport, ProgressEvent } from '../types/report'
import fixture from './report.fixture.json'

/** A real (downsampled) report produced by the backend orchestrator for the paracetamol example. */
export const reportFixture = () => structuredClone(fixture) as unknown as FullReport

export const STAGE_IDS = ['validate', 'process', 'conditions', 'sensitivity', 'pca', 'models', 'report', 'explain']

export function stageEvents(upTo = STAGE_IDS.length): ProgressEvent[] {
  return STAGE_IDS.slice(0, upTo).flatMap((id, i) => [
    { event: 'stage', stage: id, label: `Stage ${id}`, status: 'running', completed: i, total: STAGE_IDS.length },
    { event: 'stage', stage: id, label: `Stage ${id}`, status: id === 'pca' || id === 'models' ? 'skipped' : 'done', completed: i + 1, total: STAGE_IDS.length },
  ] as ProgressEvent[])
}

/** NDJSON body delivered in awkward chunks (lines split across chunks). With `gate`, events from index `gateAt` onward wait for it. */
export function ndjsonResponse(events: ProgressEvent[], { chunk = 37, gate, gateAt = 0 }: { chunk?: number; gate?: Promise<void>; gateAt?: number } = {}) {
  const enc = new TextEncoder()
  const lines = (es: ProgressEvent[]) => enc.encode(es.map(e => JSON.stringify(e) + '\n').join(''))
  const head = lines(events.slice(0, gate ? gateAt : events.length))
  const tail = lines(gate ? events.slice(gateAt) : [])
  let i = 0
  const body = new ReadableStream<Uint8Array>({
    async pull(ctrl) {
      if (i === head.length && gate) await gate
      const bytes = i < head.length ? head : tail
      const off = i < head.length ? i : i - head.length
      if (off >= bytes.length || (bytes === tail && !tail.length)) { ctrl.close(); return }
      const end = Math.min(off + chunk, bytes.length)
      ctrl.enqueue(bytes.slice(off, end))
      i += end - off
    },
  })
  return new Response(body, { status: 200, headers: { 'Content-Type': 'application/x-ndjson' } })
}
