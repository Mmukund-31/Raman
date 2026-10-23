import { describe, expect, it, vi } from 'vitest'
import { defaultOptions } from '../types'
import { emptyConditions, type AnalysisInput, type ProgressEvent } from '../types/report'
import { ndjsonResponse, reportFixture, stageEvents } from '../test/helpers'
import { applyEvent, failRunning, INITIAL_STAGES, paced, type StageState } from './progress'
import { AnalysisError, buildRequest, conditionsToMetadata, ndjsonParser, processedCsv, runAnalysis } from './report'

const input = (over: Partial<AnalysisInput> = {}): AnalysisInput => ({
  file: new File(['raman_shift_cm1,intensity\n'], 'my sample.csv', { type: 'text/csv' }), example: '', extras: [], primaryLabel: '',
  excitation: '', origin: 'unknown', conditions: { ...emptyConditions }, options: defaultOptions, ...over,
})

describe('ndjsonParser', () => {
  it('reassembles lines split across chunks and flushes the tail', () => {
    const seen: ProgressEvent[] = []
    const p = ndjsonParser(e => seen.push(e))
    p.push('{"event":"stage","stage":"va')
    p.push('lidate","status":"running"}\n{"event":"err')
    expect(seen).toHaveLength(1)
    p.push('or","stage":"validate","message":"bad"}')
    p.end()
    expect(seen.map(e => e.event)).toEqual(['stage', 'error'])
  })
})

describe('conditionsToMetadata', () => {
  it('sends only recorded fields, with units, and never invents zeros', () => {
    expect(conditionsToMetadata(emptyConditions)).toEqual({})
    const m = conditionsToMetadata({ ...emptyConditions, temperature: '25', laser_power: '0.5', laser_power_unit: 'W', geometry: ' backscattering ' })
    expect(m).toEqual({ temperature: 25, temperature_unit: 'C', laser_power: 0.5, laser_power_unit: 'W', geometry: 'backscattering' })
  })
  it('rejects non-numeric values instead of sending NaN', () => {
    expect(() => conditionsToMetadata({ ...emptyConditions, exposure_s: 'ten' })).toThrow(/exposure s/)
  })
})

describe('buildRequest', () => {
  it('uploads the file with all options, metadata and extras as a streaming request', () => {
    const extra = new File(['x'], 'rep2.csv')
    const { url, init } = buildRequest(input({ extras: [{ file: extra, label: 'B' }], excitation: '785', origin: 'measured', primaryLabel: 'A' }))
    expect(url).toMatch(/\/api\/full-report$/)
    const f = init.body as FormData
    expect(f.get('sample_id')).toBe('my sample')
    expect(f.get('stream')).toBe('true')
    expect(f.get('baseline')).toBe('true')
    expect(f.get('origin')).toBe('measured')
    expect(f.getAll('extra_files')).toHaveLength(1)
    expect(JSON.parse(f.get('extra_labels') as string)).toEqual(['B'])
  })
  it('uses the example endpoint without a file and fails clearly with neither', () => {
    expect(buildRequest(input({ file: null, example: 'demo_x' })).url).toMatch(/\/api\/full-report\/example\/demo_x\?stream=true$/)
    expect(() => buildRequest(input({ file: null }))).toThrow(AnalysisError)
  })
})

describe('runAnalysis', () => {
  it('reports every server event in order and returns the final report', async () => {
    const report = reportFixture()
    const events = [...stageEvents(), { event: 'result', report } as ProgressEvent]
    vi.stubGlobal('fetch', vi.fn(async () => ndjsonResponse(events, { chunk: 11 })))
    const seen: ProgressEvent[] = []
    const out = await runAnalysis(input(), e => seen.push(e))
    expect(out.sample_id).toBe(report.sample_id)
    expect(seen.map(e => (e.event === 'stage' ? `${e.stage}:${e.status}` : e.event))).toEqual(
      events.map(e => (e.event === 'stage' ? `${e.stage}:${e.status}` : e.event)))
  })
  it('surfaces a streamed validation error with its stage', async () => {
    const events: ProgressEvent[] = [stageEvents(1)[0], { event: 'error', stage: 'validate', message: 'Missing required columns.' }]
    vi.stubGlobal('fetch', vi.fn(async () => ndjsonResponse(events)))
    await expect(runAnalysis(input(), () => {})).rejects.toMatchObject({ message: 'Missing required columns.', stage: 'validate' })
  })
  it('never treats a truncated stream as a finished report', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ndjsonResponse(stageEvents(3))))
    await expect(runAnalysis(input(), () => {})).rejects.toThrow(/closed before the report was finished/)
  })
  it('reports HTTP errors and unreachable servers in plain language', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: 'File exceeds the 5 MB limit.' }), { status: 413 })))
    await expect(runAnalysis(input(), () => {})).rejects.toThrow('File exceeds the 5 MB limit.')
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch') }))
    await expect(runAnalysis(input(), () => {})).rejects.toThrow(/Cannot reach the analysis server/)
  })
})

describe('progress reducer', () => {
  it('changes a stage only when the server reports it', () => {
    let s = INITIAL_STAGES
    expect(s.every(x => x.status === 'pending')).toBe(true)
    const [run, done] = stageEvents(1)
    s = applyEvent(s, run)
    expect(s[0].status).toBe('running')
    expect(s.slice(1).every(x => x.status === 'pending')).toBe(true)
    s = applyEvent(s, done)
    expect(s[0]).toMatchObject({ status: 'done', label: 'Stage validate' })
  })
  it('appends unknown stages and marks failures', () => {
    let s = applyEvent(INITIAL_STAGES, { event: 'stage', stage: 'new', label: 'New step', status: 'running', completed: 7, total: 8 })
    expect(s.at(-1)).toMatchObject({ id: 'new', status: 'running' })
    s = applyEvent(s, { event: 'error', stage: 'new', message: 'boom' })
    expect(s.at(-1)?.status).toBe('error')
    expect(failRunning([{ id: 'a', label: 'A', status: 'running' }])[0].status).toBe('error')
  })
})

describe('exports', () => {
  it('writes processed data as CSV with a header and one row per point', () => {
    const r = reportFixture()
    const csv = processedCsv(r).split('\n')
    expect(csv[0]).toBe('raman_shift_cm1,raw,baseline,processed')
    expect(csv).toHaveLength(r.sections.spectrum.data.x.length + 1)
  })
})

describe('paced display', () => {
  const server = (st: StageState['status'][]) => INITIAL_STAGES.map((s, i) => ({ ...s, status: st[i] ?? 'pending' }))
  it('trails the server but never shows a step as done or started before the server has', () => {
    const s = server(['done', 'done', 'done', 'running'])
    expect(paced(s, 0).map(x => x.status)).toEqual(['running', 'pending', 'pending', 'pending', 'pending', 'pending', 'pending', 'pending'])
    expect(paced(s, 2).map(x => x.status).slice(0, 4)).toEqual(['done', 'done', 'running', 'pending'])
    expect(paced(s, 4).map(x => x.status).slice(0, 5)).toEqual(['done', 'done', 'done', 'running', 'pending'])
    expect(paced(server([]), 0)[0].status).toBe('pending')
  })
})
