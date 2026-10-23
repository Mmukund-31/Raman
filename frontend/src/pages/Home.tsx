import { lazy, Suspense, useEffect, useRef, useState, type ReactNode } from 'react'
import { COLORS } from '../components/theme'
import { BEAMS, MODULES, REPORT_FLOW, STEPS, type StepId } from '../cuberaman/layout'

const CubeRamanScene = lazy(() => import('../cuberaman/CubeRamanScene').then(m => ({ default: m.CubeRamanScene })))
export const TOUR_MS = 8000
const WRAP = 'mx-auto max-w-7xl px-4 sm:px-6'

function Kicker({ children }: { children: string }) {
  return <p className="kicker">{children}</p>
}

function SectionHead({ kicker, title, id, children }: { kicker: string; title: string; id: string; children?: ReactNode }) {
  return (
    <div className="max-w-3xl">
      <Kicker>{kicker}</Kicker>
      <h2 id={id} className="section-title mt-2">{title}</h2>
      {children && <div className="mt-3 text-lg leading-relaxed text-slate-600">{children}</div>}
    </div>
  )
}

/** Illustrative paracetamol-like spectrum (not measured data): raw counts on a fluorescence slope, then cleaned and matched. */
const BANDS = [[651, 0.35], [797, 0.55], [858, 1], [1168, 0.6], [1236, 0.45], [1324, 0.55], [1371, 0.3], [1561, 0.4], [1611, 0.75], [1648, 0.5]]
const peaks = (x: number) => BANDS.reduce((s, [c, a]) => s + a / (1 + ((x - c) / 9) ** 2), 0)
const XS = Array.from({ length: 220 }, (_, i) => 400 + (i * 1400) / 219)
const noise = (i: number) => (Math.sin(i * 12.9898) * 43758.5453) % 1
function line(f: (x: number, i: number) => number, lo: number, hi: number) {
  return XS.map((x, i) => `${((x - 400) / 1400 * 200).toFixed(1)},${(70 - ((f(x, i) - lo) / (hi - lo)) * 62).toFixed(1)}`).join(' ')
}
const SKETCHES = [
  { title: 'Raw counts', note: 'Fluorescence background and noise', paths: [{ d: line((x, i) => 1.6 + 1.2 * Math.exp(-(x - 400) / 900) + 0.6 * peaks(x) + 0.05 * noise(i), 1.4, 3.6), c: COLORS.muted }] },
  { title: 'Processed', note: 'Baseline removed, smoothed, normalised', paths: [{ d: line(x => peaks(x), 0, 1.15), c: COLORS.accent }] },
  { title: 'Matched', note: 'Compared with a reference spectrum', paths: [{ d: line(x => peaks(x - 4) * 0.82 + 0.04, 0, 1.15), c: COLORS.peak }, { d: line(x => peaks(x), 0, 1.15), c: COLORS.accent }] },
]

/** Illustrative urine model (same band model as data/urine/generate_urine_trial.py), not measured data. */
const URINE: Record<string, [number, number, number][]> = {
  base: [[1003, 1.2, 6], [1160, 0.26, 9], [1625, 0.22, 14], [546, 0.1, 10], [680, 0.6, 7], [843, 0.33, 8], [905, 0.16, 8], [1420, 0.13, 10], [640, 0.32, 8]],
  glucose: [[1125, 0.6, 9], [1060, 0.45, 10], [911, 0.3, 9], [520, 0.25, 12], [1365, 0.15, 12], [425, 0.15, 12]],
}
const UX = Array.from({ length: 351 }, (_, i) => 400 + i * 4)
const urine = (g: number) => UX.map(x => [...URINE.base, ...URINE.glucose.map(([c, h, w]) => [c, h * g, w] as [number, number, number])]
  .reduce((s, [c, h, w]) => s + h / (1 + ((x - c) / w) ** 2), 0))
const W = 560, H = 250, PAD = { l: 14, r: 14, t: 26, b: 34 }
const px = (x: number) => PAD.l + ((x - 400) / 1400) * (W - PAD.l - PAD.r)
const py = (y: number) => H - PAD.b - (y / 1.35) * (H - PAD.t - PAD.b)
const path = (ys: number[]) => ys.map((y, i) => `${i ? 'L' : 'M'}${px(UX[i]).toFixed(1)},${py(y).toFixed(1)}`).join('')

function HeroFigure() {
  const control = urine(0.02), diabetic = urine(1.4)
  const labels: [number, string, number, 'start' | 'middle' | 'end'][] = [[680, 'Creatinine', 0.62, 'middle'], [1003, 'Urea', 1.22, 'middle'], [1125, 'Glucose 1060 ·', 0.88, 'start']]
  return (
    <figure className="rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_24px_60px_-28px_rgba(15,102,68,0.35)]">
      <div className="flex items-center justify-between gap-2 px-1">
        <p className="text-xs font-semibold text-slate-700">Fig. 1 · Urine Raman fingerprint, 785 nm</p>
        <div className="flex gap-3 text-[11px] text-slate-600">
          <span className="flex items-center gap-1.5"><span className="h-0.5 w-4 rounded-full" style={{ background: '#2a78d6' }} />Normoglycaemic</span>
          <span className="flex items-center gap-1.5"><span className="h-0.5 w-4 rounded-full" style={{ background: '#eb6834' }} />Glycosuria</span>
        </div>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="mt-2 w-full" role="img" aria-label="Illustrative urine Raman spectra with and without glucose; glucose adds bands at 1060 and 1125 cm⁻¹">
        {[1060, 1125].map(c => <rect key={c} x={px(c - 14)} y={PAD.t} width={px(c + 14) - px(c - 14)} height={H - PAD.t - PAD.b} fill="#f0faf4" />)}
        {[400, 600, 800, 1000, 1200, 1400, 1600, 1800].map(x => (
          <g key={x}><line x1={px(x)} x2={px(x)} y1={H - PAD.b} y2={H - PAD.b + 4} stroke="#cbd5e1" /><text x={px(x)} y={H - PAD.b + 16} fontSize="10" textAnchor="middle" fill="#64748b">{x}</text></g>
        ))}
        <line x1={PAD.l} x2={W - PAD.r} y1={H - PAD.b} y2={H - PAD.b} stroke="#cbd5e1" />
        <text x={W / 2} y={H - 4} fontSize="10" textAnchor="middle" fill="#64748b">Raman shift (cm⁻¹)</text>
        <path d={path(control)} fill="none" stroke="#2a78d6" strokeWidth="1.8" strokeLinejoin="round" />
        <path d={path(diabetic)} fill="none" stroke="#eb6834" strokeWidth="1.8" strokeLinejoin="round" />
        {labels.map(([x, t, y, a], k) => (
          <g key={k}><line x1={px(x)} x2={px(x)} y1={py(y) - 4} y2={py(y) - 12} stroke="#94a3b8" /><text x={px(x) + (a === 'end' ? 3 : a === 'start' ? -3 : 0)} y={py(y) - 15} fontSize="10" textAnchor={a} fill="#334155">{t} {x}</text></g>
        ))}
      </svg>
      <figcaption className="px-1 pt-1 text-[11px] text-slate-500">Illustrative model spectra, not measured data. Measured cohort spectra are on the Diabetes study page.</figcaption>
    </figure>
  )
}

const STATS: [string, string, string][] = [
  ['250', 'measured urine spectra', 'Patient urine, Zenodo 7343559 (785 nm)'],
  ['127', 'from patients with diabetes', 'vs 98 CKD without diabetes, 25 healthy'],
  ['70', 'trial participants', 'Simulated · 4 visits over 12 weeks'],
  ['18', 'assigned Raman bands', 'Glucose, ketones, urea, creatinine, protein'],
]

const WORKFLOW: [string, string][] = [
  ['Collect', 'Spot urine sample, no preparation'],
  ['Acquire', '785 nm Raman spectrum, 400–1800 cm⁻¹'],
  ['Process', 'Despike, baseline, smooth, normalise'],
  ['Quantify', 'Band indices and PCA scores'],
  ['Report', 'Cohort comparison with 2D and 3D figures'],
]

function TourProgress({ active, running }: { active: boolean; running: boolean }) {
  const bar = useRef<HTMLSpanElement>(null)
  useEffect(() => {
    const a = running && active ? bar.current?.animate?.([{ transform: 'scaleX(0)' }, { transform: 'scaleX(1)' }], { duration: TOUR_MS, easing: 'linear', fill: 'forwards' }) : undefined
    return () => a?.cancel()
  }, [active, running])
  return (
    <span className={`relative h-1 flex-1 overflow-hidden rounded-full ${active ? 'bg-accent-100' : 'bg-slate-200'}`}>
      <span ref={bar} className="absolute inset-0 origin-left bg-accent-600" style={{ transform: active && !running ? 'scaleX(1)' : 'scaleX(0)' }} />
    </span>
  )
}

export function Home({ onAnalyze, onStudy }: { onAnalyze: () => void; onStudy?: () => void }) {
  const [step, setStep] = useState<StepId | null>(null)
  const [exploded, setExploded] = useState(false)
  const [inside, setInside] = useState(false)
  const [touring, setTouring] = useState(false)
  const viewer = useRef<HTMLElement>(null)
  const i = step ? STEPS.findIndex(s => s.id === step) : -1
  const current = i >= 0 ? STEPS[i] : null
  const seeInside = current ? current.inside : inside

  const go = (k: number) => { setExploded(false); setStep(STEPS[(k + STEPS.length) % STEPS.length].id) }
  const select = (s: StepId) => { setTouring(false); setExploded(false); setStep(s) }
  const overview = () => { setTouring(false); setStep(null); setExploded(false); setInside(false) }
  const startTour = () => { setStep(null); setExploded(false); setTouring(true) }

  useEffect(() => {
    if (!touring) return
    const t = setTimeout(() => (i === STEPS.length - 1 ? (setTouring(false), setStep(null)) : go(i + 1)), i < 0 ? 0 : TOUR_MS)
    return () => clearTimeout(t)
  }, [touring, i])

  const tool = (on: boolean) => `rounded-lg px-2.5 py-1.5 font-medium transition ${on ? 'bg-accent-700 text-white' : 'text-slate-600 hover:bg-slate-100'}`

  return (
    <div>
      {/* ---------------------------------------------------------------- hero */}
      <section className="bg-grid relative overflow-hidden border-b border-accent-100 bg-gradient-to-b from-accent-50 to-white">
        <div className={`${WRAP} grid items-center gap-12 py-16 lg:grid-cols-[1.05fr_1fr] lg:py-24`}>
          <div>
            <p className="inline-flex items-center gap-2 rounded-full border border-accent-200 bg-white px-3 py-1 text-xs font-medium text-accent-800">
              <span className="h-1.5 w-1.5 rounded-full bg-accent-500" /> Personalised healthcare research · Study 1: diabetes
            </p>
            <h1 className="mt-6 text-4xl font-semibold tracking-tight text-balance text-slate-900 sm:text-[54px] sm:leading-[1.05]" style={{ fontFamily: 'var(--font-serif)' }}>
              Personalised health monitoring through the Raman fingerprint of urine
            </h1>
            <p className="mt-6 max-w-xl text-lg leading-relaxed text-pretty text-slate-600">
              RamanReach turns a single laser reading of a spot urine sample into glucose, ketone and urea indices, and reads them against each person's own baseline as well as the population. Diabetes is our first study; the same approach is built to extend to kidney and metabolic health, other biofluids and personal health records.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <button className="btn-primary px-5 py-2.5" onClick={onStudy}>Explore the diabetes study →</button>
              <button className="btn-ghost px-5 py-2.5" onClick={onAnalyze}>Analyze a spectrum</button>
            </div>
            <p className="mt-6 text-xs text-slate-500">Research use only. Results complement clinical laboratory tests rather than replace them.</p>
          </div>
          <HeroFigure />
        </div>
      </section>

      {/* ---------------------------------------------------------------- key figures */}
      <section aria-label="Key figures" className="border-b border-slate-200 bg-white">
        <dl className={`${WRAP} grid grid-cols-2 divide-slate-200 py-8 lg:grid-cols-4 lg:divide-x`}>
          {STATS.map(([n, label, note]) => (
            <div key={label} className="flex flex-col px-2 py-3 lg:px-8">
              <dt className="order-2 text-sm font-medium text-slate-700">{label}</dt>
              <dd className="order-1 text-4xl font-semibold tracking-tight text-accent-700 tabular-nums" style={{ fontFamily: 'var(--font-serif)' }}>{n}</dd>
              <dd className="order-3 mt-0.5 text-xs text-slate-500">{note}</dd>
            </div>
          ))}
        </dl>
      </section>

      {/* ---------------------------------------------------------------- workflow */}
      <section aria-labelledby="workflow" className={`${WRAP} py-20`}>
        <SectionHead kicker="Method" title="From urine sample to research report" id="workflow" />
        <ol className="mt-10 grid gap-3 sm:grid-cols-5">
          {WORKFLOW.map(([t, d], k) => (
            <li key={t} className="relative rounded-2xl border border-slate-200 bg-white p-5">
              <span className="text-xs font-semibold text-accent-600 tabular-nums">0{k + 1}</span>
              <p className="mt-1 font-semibold text-slate-900">{t}</p>
              <p className="mt-1 text-sm leading-relaxed text-slate-500">{d}</p>
              {k < WORKFLOW.length - 1 && <span aria-hidden className="absolute top-1/2 -right-2.5 z-10 hidden h-5 w-5 -translate-y-1/2 items-center justify-center rounded-full bg-accent-600 text-[11px] text-white sm:flex">›</span>}
            </li>
          ))}
        </ol>
      </section>

      {/* ---------------------------------------------------------------- instrument */}
      <section aria-labelledby="instrument" className="border-t border-slate-200 bg-slate-50/60">
        <div className={`${WRAP} space-y-8 py-20`}>
          <div className="flex flex-wrap items-end justify-between gap-6">
            <SectionHead kicker="Instrument" title="Meet the CubeRaman" id="instrument">
              A 3D-printed Raman spectrometer that fits in your hand. Follow the light from the laser to a chemical fingerprint.
            </SectionHead>
            <button className="btn-ghost" onClick={() => { startTour(); viewer.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' }) }}>Start the guided tour</button>
          </div>

          <section ref={viewer} aria-label="Interactive CubeRaman model" className="card scroll-mt-24 overflow-hidden">
            <div className="grid lg:grid-cols-[minmax(0,1fr)_360px]">
              <div className="flex flex-col">
                <div className="relative h-[420px] bg-[radial-gradient(42rem_26rem_at_50%_40%,#ffffff,#e7f3ec)] sm:h-[540px]">
                  <Suspense fallback={<div className="flex h-full items-center justify-center text-sm text-slate-400">Loading 3D model…</div>}>
                    <CubeRamanScene step={step} exploded={exploded} inside={seeInside} onSelect={select} />
                  </Suspense>
                  <div className="pointer-events-none absolute inset-x-0 top-0 flex flex-wrap items-start justify-between gap-2 p-3 sm:p-4">
                    <ul className="pointer-events-auto hidden space-y-1 rounded-xl border border-slate-200 bg-white/85 px-3 py-2 text-[11px] text-slate-600 backdrop-blur sm:block" aria-label="Legend">
                      {BEAMS.filter(b => b.id === 'excitation' || b.id === 'raman' || b.id === 'rayleigh').map(b => (
                        <li key={b.id} className="flex items-center gap-2"><span className="h-1 w-4 rounded-full" style={{ background: b.colour, opacity: b.id === 'rayleigh' ? 0.5 : 1 }} />{b.label}</li>
                      ))}
                    </ul>
                    <div className="pointer-events-auto flex gap-1 rounded-xl border border-slate-200 bg-white/85 p-1 text-xs backdrop-blur" role="toolbar" aria-label="View">
                      <button onClick={overview} aria-pressed={!step && !exploded && !inside} className={tool(!step && !exploded && !inside)}>Overview</button>
                      <button onClick={() => { const next = !seeInside; overview(); setInside(next) }} aria-pressed={seeInside && !exploded} className={tool(seeInside && !exploded)}>Inside view</button>
                      <button onClick={() => { setTouring(false); setStep(null); setExploded(e => !e) }} aria-pressed={exploded} className={tool(exploded)}>Exploded</button>
                    </div>
                  </div>
                  <p className="pointer-events-none absolute bottom-3 left-4 text-[11px] text-slate-400">Drag to rotate · scroll to zoom · click a part</p>
                </div>
                <div className="flex items-center gap-1.5 border-t border-slate-200 px-4 py-3" aria-hidden>
                  {STEPS.map((s, k) => <TourProgress key={s.id} active={k <= i} running={touring && k === i} />)}
                </div>
              </div>

              <aside className="flex flex-col border-t border-slate-200 lg:border-t-0 lg:border-l">
                <ol className="border-b border-slate-200 p-2.5" aria-label="Tour steps">
                  {STEPS.map(s => (
                    <li key={s.id}>
                      <button onClick={() => select(s.id)} aria-current={step === s.id ? 'step' : undefined}
                        className={`flex w-full items-center gap-3 rounded-lg px-3 py-1.5 text-left text-sm transition ${step === s.id ? 'bg-accent-50 text-accent-700' : 'text-slate-600 hover:bg-slate-50'}`}>
                        <span className={`flex h-6 w-6 flex-none items-center justify-center rounded-full text-[11px] font-semibold tabular-nums ${step === s.id ? 'bg-accent-600 text-white' : 'bg-slate-100 text-slate-500'}`}>{s.n}</span>
                        <span className="font-medium">{s.title}</span>
                      </button>
                    </li>
                  ))}
                </ol>
                <div className="flex flex-1 flex-col p-6" aria-live="polite">
                  {current ? (
                    <div key={current.id} className="fade-up flex-1">
                      <Kicker>{`Step ${current.n} of ${STEPS.length}`}</Kicker>
                      <h3 className="mt-1 text-lg font-semibold tracking-tight text-slate-900">{current.title}</h3>
                      <p className="mt-2 font-medium leading-relaxed text-slate-800">{current.lede}</p>
                      <p className="mt-2 text-sm leading-relaxed text-slate-600">{current.body}</p>
                      <dl className="mt-4 space-y-2">
                        {MODULES.filter(m => current.modules.includes(m.id)).map(m => (
                          <div key={m.id} className="flex justify-between gap-3 border-t border-slate-100 pt-2 text-xs">
                            <dt className="font-medium text-slate-700">{m.name}</dt><dd className="text-right text-slate-500">{m.spec}</dd>
                          </div>
                        ))}
                      </dl>
                      {current.id === 'data' && <button className="btn-primary mt-5 w-full" onClick={onAnalyze}>Analyze a spectrum</button>}
                    </div>
                  ) : (
                    <div className="flex-1">
                      <Kicker>{exploded ? 'Exploded view' : 'Overview'}</Kicker>
                      <h3 className="mt-1 text-lg font-semibold tracking-tight text-slate-900">{exploded ? 'Five inserts around one cube' : 'One cube, two light paths'}</h3>
                      <p className="mt-2 text-sm leading-relaxed text-slate-600">
                        {exploded
                          ? 'Each face of the printed cube carries one insert: laser, sample, beam dump and filter & focus around the sides, and the mirror hanging from the lid. Inserts are swapped and aligned independently.'
                          : 'The green laser enters from the side and is turned 90° onto the sample. The much weaker Raman light returns along the same axis, straight through the mirror and filters, into the spectrometer behind the cube.'}
                      </p>
                      <p className="mt-3 text-sm leading-relaxed text-slate-500">Take the guided tour, or click any part of the model.</p>
                    </div>
                  )}
                  <div className="mt-6 flex items-center gap-2">
                    {current && (
                      <>
                        <button className="btn-ghost px-3" onClick={() => { setTouring(false); go(i - 1) }} aria-label="Previous step">←</button>
                        <button className="btn-ghost px-3" onClick={() => { setTouring(false); go(i + 1) }} aria-label="Next step">→</button>
                      </>
                    )}
                    <button className="btn-primary ml-auto" onClick={() => (touring ? setTouring(false) : current ? setTouring(true) : startTour())}>
                      {touring ? 'Pause tour' : current ? 'Resume tour' : 'Start the tour'}
                    </button>
                  </div>
                </div>
              </aside>
            </div>
          </section>
        </div>
      </section>

      {/* ---------------------------------------------------------------- pipeline */}
      <section aria-labelledby="flow" className={`${WRAP} space-y-8 py-20`}>
        <SectionHead kicker="From instrument to report" title="How RamanReach uses a CubeRaman spectrum" id="flow">
          The spectrometer only gives intensity per pixel. RamanReach does the rest, with the same stages it runs on every upload.
        </SectionHead>
        <div className="grid gap-4 sm:grid-cols-3">
          {SKETCHES.map(s => (
            <figure key={s.title} className="card p-4">
              <svg viewBox="0 0 200 74" className="h-24 w-full" role="img" aria-label={`${s.title} spectrum sketch`}>
                <line x1="0" y1="71" x2="200" y2="71" stroke="#e2e8f0" />
                {s.paths.map((p, k) => <polyline key={k} points={p.d} fill="none" stroke={p.c} strokeWidth={1.4} strokeLinejoin="round" opacity={s.paths.length > 1 && k === 0 ? 0.7 : 1} strokeDasharray={s.paths.length > 1 && k === 0 ? '3 2' : undefined} />)}
              </svg>
              <figcaption className="mt-2"><span className="block text-sm font-medium text-slate-900">{s.title}</span><span className="text-xs text-slate-500">{s.note}</span></figcaption>
            </figure>
          ))}
        </div>
        <p className="-mt-4 text-xs text-slate-400">Illustrative sketches, not measured data.</p>
        <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {REPORT_FLOW.map((f, k) => (
            <li key={f.title} className="rounded-xl border border-slate-200 bg-white p-4">
              <p className="text-xs font-semibold text-accent-600 tabular-nums">0{k + 1}</p>
              <p className="mt-1 font-medium text-slate-900">{f.title}</p>
              <p className="mt-1 text-sm leading-relaxed text-slate-500">{f.body}</p>
            </li>
          ))}
        </ol>
        <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-accent-200 bg-accent-50 p-6">
          <p className="mr-auto text-sm text-slate-700"><span className="font-semibold text-slate-900">Have a spectrum?</span> Upload a CSV, or try one of the bundled examples. The report shows every result in 2D and 3D.</p>
          <button className="btn-primary" onClick={onAnalyze}>Analyze a spectrum</button>
        </div>
      </section>
    </div>
  )
}
