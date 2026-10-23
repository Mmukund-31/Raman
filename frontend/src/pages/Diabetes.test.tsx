import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { PersonalIndex, UrineParticipant, UrineResult, UrineStudy } from '../types/urine'
import { Diabetes } from './Diabetes'

vi.mock('../components/report/Figure', () => ({ Figure: ({ label }: { label: string }) => <div data-testid="figure">{label}</div> }))
vi.mock('../components/report/Figure3D', () => ({
  Figure3D: ({ label }: { label: string }) => <div data-testid="figure3d">{label}</div>,
  FigurePair: ({ two, three }: { two: ReactNode; three: ReactNode }) => <div>{two}{three}</div>,
}))
afterEach(cleanup)

const grid = [600, 700, 800]
const stats = (v: number[]) => ({ n: v.length, p5: v[0], q1: v[0], median: v[1], q3: v[2], p95: v[2], values: v })
const sample = (id: string, group: string, g: number) => ({ sample_id: id, group, week: 0, participant: id, response: group === 'control' ? 'n/a' : 'responder',
  class: null, pc: [g, 0, 0], indices: { glucose: g, ketones: 0, urea: 2 }, reference_glucose_mg_dl: g * 500, cv_probability: g > 0.5 ? 0.9 : 0.1 })

function study(category: 'synthetic' | 'measured'): UrineStudy {
  const trial = category === 'synthetic'
  return {
    dataset: { dataset_id: trial ? 'trial' : 'zenodo', name: trial ? 'Simulated trial' : 'Patient urine', category, license: 'x', design: 'Design text', citation: 'Senger et al.' },
    n_spectra: 4, groups: [{ id: 'control', label: 'Normoglycaemic control', n: 2 }, { id: 'diabetes', label: 'Type 2 diabetes', n: 2 }], positive_group: 'diabetes', grid,
    mean_spectra: [{ group: 'control', label: 'Normoglycaemic control', n: 2, mean: [1, 2, 1], sd: [0.1, 0.1, 0.1] }, { group: 'diabetes', label: 'Type 2 diabetes', n: 2, mean: [1, 3, 1], sd: [0.1, 0.1, 0.1] }],
    difference: { label: 'Type 2 diabetes − Normoglycaemic control', y: [0, 1, 0] },
    bands: [{ position: 1125, solute: 'glucose', label: 'Glucose C–O–H' }, { position: 680, solute: 'creatinine', label: 'Creatinine (ring)' }],
    indices: { glucose: { label: 'Glucose index', note: 'n', bands: [1125] }, ketones: { label: 'Ketone index', note: 'n', bands: [787] }, urea: { label: 'Urea index', note: 'n', bands: [1003] } },
    index_stats: { glucose: { control: stats([0.01, 0.02, 0.03]), diabetes: stats([1, 1.5, 2]) }, ketones: { control: stats([0, 0, 0]), diabetes: stats([0, 0, 0]) }, urea: { control: stats([2, 2, 2]), diabetes: stats([2, 2, 2]) } },
    pca: { explained_variance_ratio: [0.7, 0.2, 0.05], loadings: [[0, 1, 0], [1, 0, 0], [0, 0, 1]] },
    samples: [sample('C1', 'control', 0.02), sample('C2', 'control', 0.03), sample('T1', 'diabetes', 1.2), sample('T2', 'diabetes', 1.8)],
    classification: { positive: 'diabetes', n: 4, n_positive: 2, n_folds: 2, method: 'PCA → logistic regression.', auc: 0.94, accuracy: 0.9, sensitivity: 0.85, specificity: 0.95,
      confusion: { tp: 2, fn: 0, fp: 0, tn: 2 }, threshold: 0.5, roc: { fpr: [0, 0, 1], tpr: [0, 1, 1] } },
    waterfall: [{ sample_id: 'C1', group: 'control', glucose_index: 0.02, y: [1, 2, 1] }],
    trial: trial ? {
      weeks: [0, 12], participants: [{ participant: 'C1', arm: 'control', response: 'n/a', glucose_index: [0.02, 0.03], reference_glucose: [5, 6] },
        { participant: 'T1', arm: 'diabetes', response: 'responder', glucose_index: [1.2, 0.1], reference_glucose: [1000, 50] }],
      cohort_means: [{ cohort: 'responder', label: 'Diabetes · responders', n: 1, mean: [1.2, 0.1], se: [0, 0] }],
      responder_surface: { weeks: [0, 12], grid, z: [[1, 2, 1], [1, 1, 1]] }, calibration: { slope: 0.001, intercept: 0, r: 0.96, r2: 0.92, n: 2 }, responder_median_drop: 0.85,
    } : null,
    processing: 'ALS baseline', disclaimer: 'Research analysis only; it does not diagnose, treat or cure diabetes.',
  }
}

const result: UrineResult = {
  dataset: 'trial', dataset_name: 'Simulated trial', dataset_category: 'synthetic', grid, processed: [1, 3, 1], covered_cm1: [400, 1800],
  indices: { glucose: 2.4, ketones: 0.02, urea: 1.9 }, index_position: { glucose: { control: 1, diabetes: 0.9 }, ketones: { control: 0.5, diabetes: 0.5 }, urea: { control: 0.5, diabetes: 0.5 } },
  pc: [2, 0, 0], nearest_group: 'diabetes', nearest_group_label: 'Type 2 diabetes', similarity_to_positive: 0.88, positive_group: 'diabetes', positive_label: 'Type 2 diabetes',
  flags: ['Glucose bands are stronger than in 95% of the reference cohort: consistent with glycosuria.'], disclaimer: 'Research analysis only.', sample_name: 'urine_glycosuria_synthetic', warnings: [],
}

const personalIndex = (values: number[], significant: boolean): PersonalIndex => ({
  label: 'Glucose index', values, baseline: values[0], latest: values[1], change: values[1] - values[0], change_pct: (values[1] - values[0]) / values[0],
  rcv: 0.5, significant, reference_range: [0.01, 0.05], in_reference_range: values.map(v => v <= 0.05),
})
const profile = (pid: string): UrineParticipant => {
  const control = pid === 'C1'
  const g = control ? personalIndex([0.02, 0.03], false) : personalIndex([1.2, 0.1], true)
  const rc = { sd_within: 0.0136, cv_assumed: 0.2, n_people: 30, rcv_at_zero: 0.038 }
  return {
    participant: pid, arm: control ? 'control' : 'diabetes', response: control ? 'n/a' : 'responder', group: control ? 'control' : 'diabetes', weeks: [0, 12],
    reference_group: 'control', reference_label: 'Normoglycaemic control', indices: { glucose: g, ketones: { ...g, label: 'Ketone index' }, urea: { ...g, label: 'Urea index' } },
    reference_change: { glucose: rc, ketones: rc, urea: rc }, reference_glucose_mg_dl: [1000, 50], grid, spectra: [[1, 2, 1], [1, 1, 1]], difference: [0, -1, 0], pc_path: [[1, 0, 0], [0, 0, 0]],
    insights: [control ? 'Control participant: these visits define the normal visit-to-visit variation used for everyone.'
      : "Glucose index fell 92% from this person's own baseline, more than the ±0.50 expected from normal visit-to-visit variation at that level."],
    disclaimer: 'Research analysis only.',
  }
}

function mockServer() {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const u = String(url)
    if (u.endsWith('/api/urine/study/trial')) return new Response(JSON.stringify(study('synthetic')))
    if (u.endsWith('/api/urine/study/zenodo')) return new Response(JSON.stringify(study('measured')))
    if (u.endsWith('/api/urine/examples')) return new Response(JSON.stringify([{ sample_id: 'urine_glycosuria_synthetic', file: 'g.csv', description: 'Uncontrolled diabetes: marked glycosuria', category: 'synthetic', concentrations_mg_dl: { glucose: 1400, ketones: 1 } }]))
    const person = u.match(/\/api\/urine\/participant\/(\w+)$/)
    if (person) return new Response(JSON.stringify(profile(person[1])))
    if (u.endsWith('/api/urine/analyze')) { expect((init!.body as FormData).get('example')).toBe('urine_glycosuria_synthetic'); return new Response(JSON.stringify(result)) }
    throw new Error(`unexpected ${u}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('Diabetes study page', () => {
  it('loads the simulated trial and shows every section with paired 2D and 3D figures', async () => {
    mockServer()
    render(<Diabetes />)
    expect(await screen.findByRole('heading', { name: 'Monitoring response to therapy over 12 weeks' })).toBeTruthy()
    expect(screen.getByText('Simulated data')).toBeTruthy()
    for (const h of ['What diabetic urine looks like to a Raman spectrometer', 'Principal component analysis of the whole spectrum', 'Place your own urine spectrum in the study'])
      expect(screen.getByRole('heading', { name: h })).toBeTruthy()
    expect(screen.getAllByTestId('figure').length).toBeGreaterThan(5)
    expect(screen.getAllByTestId('figure3d').length).toBeGreaterThanOrEqual(6)
    expect(screen.getByText('0.94')).toBeTruthy()
    expect(screen.getByText('r = 0.96')).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'From diabetes to personalised healthcare' })).toBeTruthy()
    expect(screen.getByText('Study 1').closest('li')!.textContent).toContain('Active')
    expect(screen.getByText('Study 4').closest('li')!.textContent).toContain('Planned')
  })

  it('reads one participant against their own baseline and switches between people', async () => {
    mockServer()
    render(<Diabetes />)
    expect(await screen.findByRole('heading', { name: 'From population averages to the individual' })).toBeTruthy()
    const readout = await screen.findByLabelText('Personalised read-out')
    expect(readout.textContent).toContain('T1')
    expect(readout.textContent).toContain('own baseline')
    expect(readout.textContent).toContain('Meaningful fall')
    fireEvent.change(screen.getByLabelText('Participant'), { target: { value: 'C1' } })
    expect(await screen.findByText(/these visits define the normal visit-to-visit variation/)).toBeTruthy()
    expect(screen.getByLabelText('Personalised read-out').textContent).toContain('Within normal variation')
    expect(screen.getByText(/is an assumption until repeat samples/)).toBeTruthy()
  })

  it('switches to the measured dataset, which has no trial section', async () => {
    const f = mockServer()
    render(<Diabetes />)
    await screen.findByText('Simulated data')
    fireEvent.click(screen.getByRole('radio', { name: /Patient urine/ }))
    expect(await screen.findByText('Measured data')).toBeTruthy()
    expect(f.mock.calls.some(([u]) => String(u).endsWith('/api/urine/study/zenodo'))).toBe(true)
    expect(screen.queryByRole('heading', { name: 'Monitoring response to therapy over 12 weeks' })).toBeNull()
  })

  it('analyses an example urine spectrum and states the result is not diagnostic', async () => {
    mockServer()
    render(<Diabetes />)
    fireEvent.click(await screen.findByRole('button', { name: 'Analyse' }))
    const out = await screen.findByLabelText('Urine sample result')
    expect(out.textContent).toContain('Closest cohort: Type 2 diabetes')
    expect(out.textContent).toContain('consistent with glycosuria')
    expect(out.textContent).toContain('not a probability of disease')
  })
})
