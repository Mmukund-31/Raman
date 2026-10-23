import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { INITIAL_STAGES, type StageState } from '../services/progress'
import { AnalysisLoader } from './AnalysisLoader'

afterEach(cleanup)

const withStatus = (statuses: StageState['status'][]): StageState[] => INITIAL_STAGES.map((s, i) => ({ ...s, status: statuses[i] ?? 'pending' }))

describe('AnalysisLoader', () => {
  it('shows the heading and counts only stages the server finished', () => {
    render(<AnalysisLoader name="sample.csv" stages={withStatus(['done', 'done', 'running'])} onCancel={() => {}} />)
    expect(screen.getByRole('heading', { name: 'Analyzing your spectrum…' })).toBeTruthy()
    expect(screen.getByText(`2 of ${INITIAL_STAGES.length} steps finished`)).toBeTruthy()
    const bar = screen.getByRole('progressbar')
    expect(bar.getAttribute('aria-valuenow')).toBe('2')
    expect(screen.queryByText(/%/)).toBeNull() // no invented percentages
    const items = screen.getAllByRole('listitem').map(li => li.getAttribute('data-status'))
    expect(items).toEqual(['done', 'done', 'running', 'pending', 'pending', 'pending', 'pending', 'pending'])
  })

  it('labels skipped stages as lacking data rather than complete', () => {
    render(<AnalysisLoader name="s" stages={withStatus(['done', 'done', 'done', 'done', 'skipped'])} />)
    expect(screen.getByText('not enough data')).toBeTruthy()
  })

  it('shows the error with retry and back actions, and no cancel', () => {
    const retry = vi.fn()
    const back = vi.fn()
    render(<AnalysisLoader name="bad.csv" stages={withStatus(['error'])} error="Missing required columns." onRetry={retry} onBack={back} onCancel={() => {}} />)
    expect(screen.getByRole('heading', { name: 'The analysis could not finish' })).toBeTruthy()
    expect(screen.getByRole('alert').textContent).toContain('Missing required columns.')
    expect(screen.queryByRole('button', { name: 'Cancel' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    fireEvent.click(screen.getByRole('button', { name: 'Choose another file' }))
    expect(retry).toHaveBeenCalledOnce()
    expect(back).toHaveBeenCalledOnce()
  })
})
