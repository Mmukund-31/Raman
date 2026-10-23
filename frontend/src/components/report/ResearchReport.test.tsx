import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { reportFixture } from '../../test/helpers'
import { ResearchReport } from './ResearchReport'

vi.mock('./Figure', () => ({ Figure: ({ label }: { label: string }) => <div data-testid="figure">{label}</div> }))
afterEach(cleanup)

describe('ResearchReport', () => {
  it('presents a concise research report built from the brief', () => {
    const r = reportFixture()
    render(<ResearchReport r={r} onNew={() => {}} />)
    expect(screen.getByRole('heading', { name: 'Raman Spectral Analysis' })).toBeTruthy()
    expect(screen.getAllByText(r.brief.headline).length).toBeGreaterThan(0)
    for (const h of ['Summary of findings', 'Reliability', 'Figure 1 · Processed spectrum', 'Table 1 · Principal peaks', 'Table 2 · Reference comparison', 'Conclusion and recommendations'])
      expect(screen.getByRole('heading', { name: h })).toBeTruthy()
    for (const m of r.brief.metrics) expect(screen.getByText(m.label)).toBeTruthy()
    expect(screen.getAllByTestId('figure')).toHaveLength(1)
    expect(screen.getAllByRole('row')).toHaveLength(r.brief.peaks.length + 1)
  })

  it('states the limits and the analyses that were not performed', () => {
    const r = reportFixture()
    render(<ResearchReport r={r} onNew={() => {}} />)
    expect(screen.getByText(/Not a probability of identity/)).toBeTruthy()
    expect(screen.getByText(/Not performed:/).parentElement?.textContent).toContain('requires a labelled training dataset')
    for (const l of r.brief.limitations) expect(screen.getByText(l)).toBeTruthy()
  })

  it('shows an inconclusive verdict without claiming a match', () => {
    const r = reportFixture()
    r.brief = { ...r.brief, verdict: 'Inconclusive', match_claimed: false, headline: 'No reliable match to the reference library could be established.' }
    render(<ResearchReport r={r} onNew={() => {}} />)
    expect(screen.getByRole('status').textContent).toContain('Inconclusive')
    expect(screen.getByText(/does not meet the criteria for a match claim/)).toBeTruthy()
  })

  it('exports data and starts a new analysis', () => {
    Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:x'), revokeObjectURL: vi.fn() })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const onNew = vi.fn()
    render(<ResearchReport r={reportFixture()} onNew={onNew} />)
    fireEvent.click(screen.getByRole('button', { name: 'Export data' }))
    fireEvent.click(screen.getByRole('button', { name: 'New analysis' }))
    expect(click).toHaveBeenCalledOnce()
    expect(onNew).toHaveBeenCalledOnce()
  })
})
