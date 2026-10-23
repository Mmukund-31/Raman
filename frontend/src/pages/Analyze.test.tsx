import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { STEP_MS } from '../services/progress'
import { ndjsonResponse, reportFixture, stageEvents } from '../test/helpers'
import type { ProgressEvent } from '../types/report'
import { Analyze } from './Analyze'

vi.mock('../components/report/Figure', () => ({ Figure: ({ label }: { label: string }) => <div data-testid="figure">{label}</div> }))

const examples = [{ sample_id: 'demo_paracetamol_synthetic', description: 'Paracetamol-like bands', category: 'synthetic' }]
const testFiles = [{ id: 'calcite_json', file: 'calcite.json', description: 'Calcite as JSON arrays.', tests: ['JSON'], source: 'derived', license: 'RRUFF', size_bytes: 10, expected: { expect: 'match', material: 'calcite' } }]
const full = (): ProgressEvent[] => [...stageEvents(), { event: 'result', report: reportFixture() }]

function mockServer(...analyses: (() => Response)[]) {
  const queue = [...analyses]
  const fetchMock = vi.fn(async (url: string, _init?: RequestInit) => {
    if (String(url).endsWith('/api/examples')) return new Response(JSON.stringify(examples))
    if (String(url).endsWith('/api/test-files')) return new Response(JSON.stringify(testFiles))
    const next = queue.shift()
    if (!next) throw new Error('unexpected request')
    return next()
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const upload = (name = 'sample.csv') => fireEvent.change(screen.getByLabelText('Spectrum file'),
  { target: { files: [new File(['raman_shift_cm1,intensity\n'], name, { type: 'text/csv' })] } })
/** Advance fake time in small steps so React can re-render and schedule the next paced step in between. */
async function tick(ms: number) {
  for (let t = 0; t < ms; t += 50) await act(() => vi.advanceTimersByTimeAsync(Math.min(50, ms - t)))
}
const statuses = () => [...document.querySelectorAll('[data-status]')].map(e => e.getAttribute('data-status'))

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  window.scrollTo = vi.fn() as unknown as typeof window.scrollTo
})
afterEach(() => { cleanup(); vi.useRealTimers() })

describe('Analyze workflow', () => {
  it('starts on upload with no settings to fill in', async () => {
    mockServer(() => ndjsonResponse(full()))
    render(<Analyze />)
    expect(screen.queryByRole('button', { name: 'Analyze' })).toBeNull()
    expect(screen.queryAllByRole('textbox')).toHaveLength(0)
    upload()
    expect(await screen.findByRole('heading', { name: 'Analyzing your spectrum…' })).toBeTruthy()
  })

  it('paces the steps to about five seconds even when the server is instant, then shows the report', async () => {
    mockServer(() => ndjsonResponse(full()))
    render(<Analyze />)
    upload()
    await tick(50)
    expect(statuses()).toEqual(['running', 'pending', 'pending', 'pending', 'pending', 'pending', 'pending', 'pending'])
    await tick(STEP_MS * 3)
    expect(statuses().slice(0, 4)).toEqual(['done', 'done', 'done', 'running'])
    expect(screen.queryByRole('heading', { name: 'Spectrum analysis report' })).toBeNull()
    await tick(STEP_MS * 5 + 500)
    expect(screen.getByRole('heading', { name: 'Spectrum analysis report' })).toBeTruthy()
  })

  it('never shows a step finished before the server has finished it', async () => {
    let release!: () => void
    const gate = new Promise<void>(r => { release = r })
    mockServer(() => ndjsonResponse(full(), { gate, gateAt: 7 })) // server is still running the sensitivity step
    render(<Analyze />)
    upload()
    await tick(STEP_MS * 10)
    expect(statuses()).toEqual(['done', 'done', 'done', 'running', 'pending', 'pending', 'pending', 'pending'])
    expect(screen.queryByRole('heading', { name: 'Spectrum analysis report' })).toBeNull()
    release()
    await tick(STEP_MS * 6)
    expect(screen.getByRole('heading', { name: 'Spectrum analysis report' })).toBeTruthy()
  })

  it('shows a clear error and retries', async () => {
    const fail: ProgressEvent[] = [stageEvents(1)[0], { event: 'error', stage: 'validate', message: "Missing required columns. Expected 'raman_shift_cm1'." }]
    const fetchMock = mockServer(() => ndjsonResponse(fail), () => ndjsonResponse(full()))
    render(<Analyze />)
    upload()
    expect((await screen.findByRole('alert')).textContent).toContain('Missing required columns')
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    await tick(STEP_MS * 9 + 500)
    expect(screen.getByRole('heading', { name: 'Spectrum analysis report' })).toBeTruthy()
    expect(fetchMock.mock.calls.filter(c => String(c[0]).includes('/api/full-report'))).toHaveLength(2)
  })

  it('asks only for the excitation wavelength when a wavelength file needs it', async () => {
    const fail: ProgressEvent[] = [{ event: 'error', stage: 'validate', message: 'Wavelength input needs a positive excitation wavelength (nm) to convert to Raman shift.' }]
    const fetchMock = mockServer(() => ndjsonResponse(fail), () => ndjsonResponse(full()))
    render(<Analyze />)
    upload('wl.csv')
    await screen.findByRole('alert')
    expect(screen.queryByRole('button', { name: 'Try again' })).toBeNull()
    fireEvent.change(screen.getByPlaceholderText('e.g. 785 nm'), { target: { value: '785' } })
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    await tick(STEP_MS * 9 + 500)
    const body = fetchMock.mock.calls.filter(c => String(c[0]).includes('/api/full-report'))[1][1] as RequestInit
    expect((body.body as FormData).get('excitation_nm')).toBe('785')
  })

  it('lists downloadable test files with their expected result', async () => {
    mockServer()
    render(<Analyze />)
    expect(await screen.findByText('calcite.json')).toBeTruthy()
    expect(screen.getByText('Expected: calcite')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Download all (zip)' }).getAttribute('href')).toContain('/api/test-files/all.zip')
  })

  it('runs a bundled sample with one click', async () => {
    const fetchMock = mockServer(() => ndjsonResponse(full()))
    render(<Analyze />)
    fireEvent.click(await screen.findByRole('button', { name: 'paracetamol' }))
    await tick(STEP_MS * 9 + 500)
    expect(screen.getByRole('heading', { name: 'Spectrum analysis report' })).toBeTruthy()
    expect(fetchMock.mock.calls.some(c => String(c[0]).includes('/api/full-report/example/demo_paracetamol_synthetic'))).toBe(true)
  })
})
