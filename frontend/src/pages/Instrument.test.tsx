import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { STEPS } from '../instrument/model'
import { Instrument } from './Instrument'

// WebGL is unavailable in jsdom; the stub reports the props the real scene would receive.
vi.mock('../instrument/CubeScene', () => ({
  CubeScene: ({ step, exploded }: { step: string | null; exploded: boolean }) => <div data-testid="scene" data-step={step ?? ''} data-exploded={String(exploded)} />,
}))
afterEach(() => { cleanup(); vi.useRealTimers() })

const scene = async () => screen.findByTestId('scene')

describe('Instrument page', () => {
  it('starts in the overview and lets the user pick a step', async () => {
    render(<Instrument onAnalyze={() => {}} />)
    expect((await scene()).dataset.step).toBe('')
    fireEvent.click(screen.getByRole('button', { name: /Dichroic beamsplitter/ }))
    expect((await scene()).dataset.step).toBe('dichroic')
    expect(screen.getByText('Step 2 of 6')).toBeTruthy()
    expect(screen.getByText('550 nm longpass · 45°')).toBeTruthy()
  })

  it('moves between steps and wraps around', async () => {
    render(<Instrument onAnalyze={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: /Dispersion and detection/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Next step' }))
    expect((await scene()).dataset.step).toBe('laser')
    fireEvent.click(screen.getByRole('button', { name: 'Previous step' }))
    expect((await scene()).dataset.step).toBe('spectrometer')
  })

  it('plays the guided tour through every step and returns to the overview', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    render(<Instrument onAnalyze={() => {}} />)
    await scene()
    fireEvent.click(screen.getByRole('button', { name: 'Start the tour' }))
    const seen: string[] = []
    for (let k = 0; k < STEPS.length + 1; k++) {
      await act(() => vi.advanceTimersByTimeAsync(k === 0 ? 10 : 7000))
      seen.push(screen.getByTestId('scene').dataset.step!)
    }
    expect(seen).toEqual([...STEPS.map(s => s.id), ''])
  })

  it('toggles the exploded view', async () => {
    render(<Instrument onAnalyze={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: 'Exploded view' }))
    expect((await scene()).dataset.exploded).toBe('true')
  })

  it('uses no copied images, keeps the laser-safety warning and links back to analysis', async () => {
    const onAnalyze = vi.fn()
    render(<Instrument onAnalyze={onAnalyze} />)
    await scene()
    expect(document.querySelectorAll('img')).toHaveLength(0)
    expect(screen.getByText(/Class 3B/, { selector: 'p' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Analyze a spectrum' }))
    expect(onAnalyze).toHaveBeenCalledOnce()
  })
})
