import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { reportFixture } from '../../test/helpers'
import { ResearchReport } from './ResearchReport'

vi.mock('./Figure', () => ({ Figure: ({ label }: { label: string }) => <div data-testid="figure">{label}</div> }))
vi.mock('./Figure3D', () => ({
  Figure3D: ({ label }: { label: string }) => <div data-testid="figure3d">{label}</div>,
  FigurePair: ({ two, three }: { two: ReactNode; three: ReactNode }) => <div>{two}{three}</div>,
}))
afterEach(cleanup)

const section = (name: string) => screen.getByRole('heading', { name }).parentElement!

describe('ResearchReport', () => {
  it('is laid out as a numbered lab report that leads with the result', () => {
    const r = reportFixture()
    render(<ResearchReport r={r} onNew={() => {}} />)
    expect(screen.getByRole('heading', { name: 'Spectrum analysis report' })).toBeTruthy()
    expect(screen.getByText(r.brief.report_id, { selector: 'dd' })).toBeTruthy()
    const order = ['Sample information', 'Result summary', 'Spectral comparison', 'Candidate ranking', 'Quality control', 'Interpretation', 'Recommendations']
      .map(h => screen.getByRole('heading', { name: h }))
    for (let i = 1; i < order.length; i++) expect(order[i - 1].compareDocumentPosition(order[i]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(screen.getByRole('region', { name: 'Answer' }).textContent).toContain(r.explanation!.headline)
    expect(section('Sample information').textContent).toContain(r.sample_id)
    expect(screen.getAllByTestId('figure')[0].textContent).toContain('overlaid on the best-matching reference')
    expect(screen.getAllByTestId('figure3d')[0].textContent).toContain('3D waterfall')
    expect(screen.getByText('Figure 1.')).toBeTruthy()
  })

  it('explains the candidate order with similarity, coverage and ranking score', () => {
    const r = reportFixture()
    r.visual!.candidates.items = [
      { name: 'Ethanol', score: 0.99, category: 'synthetic', coverage: 1, rank_score: 0.99, top: true },
      { name: 'Boron trioxide', score: 0.76, category: 'measured', coverage: 0.95, rank_score: 0.76, top: false },
      { name: 'Grossular', score: 0.83, category: 'measured', coverage: 0.4, rank_score: 0.47, top: false },
      { name: 'Polypropylene', score: 0.44, category: 'synthetic', coverage: 1, rank_score: 0.44, top: false },
    ]
    render(<ResearchReport r={r} onNew={() => {}} />)
    const ranking = section('Candidate ranking')
    for (const h of ['Rank', 'Candidate material', 'Similarity', 'Coverage', 'Ranking score']) expect(within(ranking).getByRole('columnheader', { name: h })).toBeTruthy()
    const grossular = within(ranking).getByText('Grossular').closest('tr')!
    expect(grossular.textContent).toContain('0.83')
    expect(grossular.textContent).toContain('40%')
    expect(grossular.textContent).toContain('0.47')
    expect(grossular.textContent).toContain('Measured reference')
    expect(within(ranking).getByText('Polypropylene').closest('tr')!.textContent).toContain('†')
  })

  it('ranks every candidate and labels each quality check without relying on colour', () => {
    const r = reportFixture()
    render(<ResearchReport r={r} onNew={() => {}} />)
    const ranking = section('Candidate ranking')
    expect(within(ranking).getAllByRole('row')).toHaveLength(r.visual!.candidates.items.length + 1)
    for (const c of r.visual!.candidates.items) expect(within(ranking).getAllByText(c.score.toFixed(2)).length).toBeGreaterThan(0)
    const checks = section('Quality control')
    expect(within(checks).getAllByRole('listitem')).toHaveLength(r.visual!.checks.length)
    for (const c of r.visual!.checks) expect(within(checks).getByText(c.label).closest('li')!.textContent).toContain(c.passed ? 'PASS' : 'FAIL')
  })

  it('states the result neutrally at every confidence level, never as a demo', () => {
    const cases: [0 | 1 | 2 | 3, string][] = [[3, 'Confirmed match'], [2, 'Probable match'], [1, 'Closest reference match'], [0, 'No confident match']]
    for (const [level, word] of cases) {
      const r = reportFixture()
      r.visual!.confidence = { level, label: 'x', reason: 'y' }
      render(<ResearchReport r={r} onNew={() => {}} />)
      const answer = screen.getByRole('region', { name: 'Answer' })
      expect(answer.textContent).toContain(word)
      expect(answer.textContent).toContain('Quality checks')
      expect(screen.queryByText(/demo result/i)).toBeNull()
      cleanup()
    }
  })

  it('keeps the specialist material in a collapsed technical appendix', () => {
    const r = reportFixture()
    render(<ResearchReport r={r} onNew={() => {}} />)
    const tech = screen.getByText('Technical appendix').closest('details')!
    expect(tech.open).toBe(false)
    expect(tech.textContent).toContain('Principal peaks')
    expect(tech.textContent).toContain('requires a labelled training dataset')
    for (const l of r.brief.limitations) expect(tech.textContent).toContain(l)
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
