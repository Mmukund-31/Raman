import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { reportFixture } from '../../test/helpers'
import { ResearchReport } from './ResearchReport'

vi.mock('./Figure', () => ({ Figure: ({ label }: { label: string }) => <div data-testid="figure">{label}</div> }))
afterEach(cleanup)

describe('ResearchReport', () => {
  it('leads with a short, picture-first answer', () => {
    const r = reportFixture()
    render(<ResearchReport r={r} onNew={() => {}} />)
    expect(screen.getByRole('heading', { name: 'Spectrum analysis report' })).toBeTruthy()
    const answer = screen.getByRole('region', { name: 'Answer' })
    expect(answer.textContent).toContain(r.explanation!.headline)
    for (const h of [`Your spectrum next to ${r.visual!.overlay.reference_name}`, 'How close were the candidates?', 'Checks we ran', 'What this means', 'What to do next'])
      expect(screen.getByRole('heading', { name: h })).toBeTruthy()
    expect(screen.getAllByTestId('figure')[0].textContent).toContain('overlaid on the best-matching reference')
  })

  it('draws one bar per candidate and one line per check, each readable without colour', () => {
    const r = reportFixture()
    render(<ResearchReport r={r} onNew={() => {}} />)
    for (const c of r.visual!.candidates.items) expect(screen.getAllByText(c.score.toFixed(2)).length).toBeGreaterThan(0)
    const checks = screen.getByRole('heading', { name: 'Checks we ran' }).parentElement!
    expect(within(checks).getAllByRole('listitem')).toHaveLength(r.visual!.checks.length)
    for (const c of r.visual!.checks) expect(within(checks).getByText(c.label).parentElement!.textContent).toContain(c.passed ? 'passed' : 'not passed')
  })

  it('shows the confidence meter, or a demo notice for simulated references', () => {
    const r = reportFixture()
    r.visual!.confidence = { level: 3, label: 'Confident', reason: 'A very close match.' }
    render(<ResearchReport r={r} onNew={() => {}} />)
    expect(screen.getByRole('meter', { name: 'Confidence' }).getAttribute('aria-valuetext')).toBe('Confident')
    expect(screen.getByText('Match found')).toBeTruthy()
    cleanup()
    const d = reportFixture()
    render(<ResearchReport r={d} onNew={() => {}} />)
    expect(screen.getByText('Demo result')).toBeTruthy()
    expect(screen.queryByRole('meter')).toBeNull()
  })

  it('says plainly when nothing can be named', () => {
    const r = reportFixture()
    r.visual!.confidence = { level: 0, label: "Can't tell", reason: 'Not all checks passed.' }
    r.visual!.candidates.named = false
    render(<ResearchReport r={r} onNew={() => {}} />)
    expect(screen.getByText('No clear match')).toBeTruthy()
    expect(screen.getByRole('meter', { name: 'Confidence' }).getAttribute('aria-valuetext')).toBe("Can't tell")
  })

  it('keeps the specialist material behind Technical details', () => {
    const r = reportFixture()
    render(<ResearchReport r={r} onNew={() => {}} />)
    const tech = screen.getByText('Technical details').closest('details')!
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
