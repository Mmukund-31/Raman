/** The personalised-healthcare research programme; diabetes and urine is the first study. Statuses are kept honest. */
export type PhaseStatus = 'Active' | 'Data available' | 'Planned'

export const PROGRAMME: { phase: string; status: PhaseStatus; title: string; body: string; items: string[] }[] = [
  {
    phase: 'Study 1', status: 'Active', title: 'Diabetes & urine',
    body: 'Glycosuria screening and therapy monitoring from urine Raman spectra, read both at population level and against each person\'s own baseline.',
    items: ['Measured cohort, 250 patient spectra', 'Simulated 12-week monitoring trial', 'Personal profiles and reference change values'],
  },
  {
    phase: 'Study 2', status: 'Data available', title: 'Kidney & metabolic health',
    body: 'Diabetic kidney disease, albuminuria and ketoacidosis risk. The measured dataset already labels diabetic nephropathy and other glomerular pathologies.',
    items: ['Diabetic vs immune-mediated nephropathy', 'Protein (amide I) and ketone bands', 'Kidney-function context for diabetes'],
  },
  {
    phase: 'Study 3', status: 'Planned', title: 'Multi-biofluid profiling',
    body: 'The same pipeline applied to saliva, sweat and serum, so that one person can be profiled across several biofluids.',
    items: ['Biofluid-specific band libraries', 'Shared preprocessing and quality gate', 'Cross-fluid consistency checks'],
  },
  {
    phase: 'Study 4', status: 'Planned', title: 'Personal health baselines',
    body: 'Longitudinal models per person that combine Raman profiles with clinical values such as HbA1c and eGFR, and flag changes relative to the individual rather than to population cut-offs.',
    items: ['Per-person baselines and change limits', 'Integration with clinical records', 'Clinician-facing trend reports'],
  },
]

export const STATUS_STYLE: Record<PhaseStatus, string> = {
  Active: 'bg-accent-600 text-white',
  'Data available': 'bg-sky-50 text-sky-800 ring-1 ring-sky-200',
  Planned: 'bg-slate-100 text-slate-600 ring-1 ring-slate-200',
}
