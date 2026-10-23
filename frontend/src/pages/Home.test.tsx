import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { STEPS } from '../cuberaman/layout'
import { Home, TOUR_MS } from './Home'

// WebGL is unavailable in jsdom; the stub reports the props the real scene would receive.
vi.mock('../cuberaman/CubeRamanScene', () => ({
  CubeRamanScene: ({ step, exploded, inside }: { step: string | null; exploded: boolean; inside: boolean }) =>
    <div data-testid="scene" data-step={step ?? ''} data-exploded={String(exploded)} data-inside={String(inside)} />,
}))
afterEach(() => { cleanup(); vi.useRealTimers() })

const scene = async () => screen.findByTestId('scene')
const noop = () => {}

describe('Home page', () => {
  it('opens on the assembled overview and lets the user pick a step', async () => {
    render(<Home onAnalyze={noop} onInstrument={noop} />)
    const s = await scene()
    expect(s.dataset.step).toBe('')
    expect(s.dataset.inside).toBe('false')
    fireEvent.click(screen.getByRole('button', { name: /Dichroic mirror/ }))
    expect((await scene()).dataset.step).toBe('mirror')
    expect((await scene()).dataset.inside).toBe('true')
    expect(screen.getByText('Step 2 of 8')).toBeTruthy()
    expect(screen.getByText('DMLP550 · Ø1″ · 45°')).toBeTruthy()
  })

  it('plays the guided tour through every step and returns to the overview', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    render(<Home onAnalyze={noop} onInstrument={noop} />)
    await scene()
    fireEvent.click(screen.getByRole('button', { name: 'Start the tour' }))
    const seen: string[] = []
    for (let k = 0; k < STEPS.length + 1; k++) {
      await act(() => vi.advanceTimersByTimeAsync(k === 0 ? 10 : TOUR_MS))
      seen.push(screen.getByTestId('scene').dataset.step!)
    }
    expect(seen).toEqual([...STEPS.map(s => s.id), ''])
  })

  it('pauses the tour when the user takes over, and wraps with the arrows', async () => {
    render(<Home onAnalyze={noop} onInstrument={noop} />)
    fireEvent.click(screen.getByRole('button', { name: /From counts to a report/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Next step' }))
    expect((await scene()).dataset.step).toBe('laser')
    fireEvent.click(screen.getByRole('button', { name: 'Previous step' }))
    expect((await scene()).dataset.step).toBe('data')
  })

  it('toggles the inside and exploded views', async () => {
    render(<Home onAnalyze={noop} onInstrument={noop} />)
    fireEvent.click(screen.getByRole('button', { name: 'Inside view' }))
    expect((await scene()).dataset.inside).toBe('true')
    fireEvent.click(screen.getByRole('button', { name: 'Exploded' }))
    expect((await scene()).dataset.exploded).toBe('true')
    fireEvent.click(screen.getByRole('button', { name: 'Overview' }))
    expect((await scene()).dataset.exploded).toBe('false')
  })

  it('explains the report pipeline, credits the source and links onward', async () => {
    const onAnalyze = vi.fn(), onInstrument = vi.fn()
    render(<Home onAnalyze={onAnalyze} onInstrument={onInstrument} />)
    await scene()
    expect(screen.getByRole('heading', { name: 'How RamanReach uses a CubeRaman spectrum' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'CubeRaman' }).getAttribute('href')).toBe('https://github.com/jacobbusshart/CubeRaman')
    expect(document.querySelectorAll('img')).toHaveLength(0)
    expect(screen.getByText(/Class 3B/, { selector: 'p' })).toBeTruthy()
    fireEvent.click(screen.getAllByRole('button', { name: 'Analyze a spectrum' })[0])
    expect(onAnalyze).toHaveBeenCalledOnce()
    fireEvent.click(screen.getByRole('button', { name: /More on how the optics work/ }))
    expect(onInstrument).toHaveBeenCalledOnce()
  })
})
