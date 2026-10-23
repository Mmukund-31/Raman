import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { COLORS } from '../components/theme'
import { BEAMS, MODULES, REPORT_FLOW, SPECS, STEPS, type StepId } from '../cuberaman/layout'

const CubeRamanScene = lazy(() => import('../cuberaman/CubeRamanScene').then(m => ({ default: m.CubeRamanScene })))
const REPO = 'https://github.com/jacobbusshart/CubeRaman'
export const TOUR_MS = 8000

function Kicker({ children }: { children: string }) {
  return <p className="text-[11px] font-semibold tracking-[0.14em] text-accent-700 uppercase">{children}</p>
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

export function Home({ onAnalyze, onInstrument }: { onAnalyze: () => void; onInstrument: () => void }) {
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

  const tool = (on: boolean) => `rounded-lg px-2.5 py-1.5 font-medium transition ${on ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'}`

  return (
    <div className="space-y-20">
      <section className="mx-auto max-w-3xl pt-6 text-center sm:pt-10">
        <p className="inline-flex items-center gap-2 rounded-full border border-accent-100 bg-accent-50 px-3 py-1 text-xs font-medium text-accent-700">
          <span className="h-1.5 w-1.5 rounded-full bg-accent-500" /> Open-source Raman spectroscopy
        </p>
        <h1 className="mt-5 text-4xl font-semibold tracking-tight text-balance text-slate-900 sm:text-5xl">Meet the CubeRaman</h1>
        <p className="mx-auto mt-4 max-w-xl text-lg leading-relaxed text-pretty text-slate-500">
          A 3D-printed Raman spectrometer that fits in your hand. Follow the light from a green laser to a chemical fingerprint, then see how RamanReach turns that spectrum into a report.
        </p>
        <div className="mt-7 flex flex-wrap justify-center gap-3">
          <button className="btn-primary px-5 py-2.5" onClick={() => { startTour(); viewer.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' }) }}>Start the guided tour</button>
          <button className="btn-ghost px-5 py-2.5" onClick={onAnalyze}>Analyze a spectrum</button>
        </div>
      </section>

      <section ref={viewer} aria-label="Interactive CubeRaman model" className="card scroll-mt-6 overflow-hidden">
        <div className="grid lg:grid-cols-[minmax(0,1fr)_360px]">
          <div className="flex flex-col">
            <div className="relative h-[420px] bg-[radial-gradient(42rem_26rem_at_50%_40%,#ffffff,#e9eef6)] sm:h-[540px]">
              <Suspense fallback={<div className="flex h-full items-center justify-center text-sm text-slate-400">Loading 3D model…</div>}>
                <CubeRamanScene step={step} exploded={exploded} inside={seeInside} onSelect={select} />
              </Suspense>
              <div className="pointer-events-none absolute inset-x-0 top-0 flex flex-wrap items-start justify-between gap-2 p-3 sm:p-4">
                <ul className="pointer-events-auto hidden space-y-1 rounded-xl sm:block border border-slate-200 bg-white/85 px-3 py-2 text-[11px] text-slate-600 backdrop-blur" aria-label="Legend">
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
                  <h2 className="mt-1 text-lg font-semibold tracking-tight text-slate-900">{current.title}</h2>
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
                  <h2 className="mt-1 text-lg font-semibold tracking-tight text-slate-900">{exploded ? 'Five inserts around one cube' : 'One cube, two light paths'}</h2>
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

      <section aria-labelledby="flow" className="space-y-8">
        <div className="max-w-2xl">
          <Kicker>From instrument to report</Kicker>
          <h2 id="flow" className="mt-2 text-2xl font-semibold tracking-tight text-slate-900 sm:text-3xl">How RamanReach uses a CubeRaman spectrum</h2>
          <p className="mt-3 leading-relaxed text-slate-600">
            The spectrometer only gives intensity per pixel. RamanReach does the rest, with the same stages it runs on every upload.
          </p>
        </div>
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
        <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-accent-100 bg-accent-50 p-5">
          <p className="mr-auto text-sm text-slate-700"><span className="font-semibold text-slate-900">Have a spectrum?</span> Upload a CSV, or try one of the bundled examples.</p>
          <button className="btn-primary" onClick={onAnalyze}>Analyze a spectrum</button>
        </div>
      </section>

      <section aria-labelledby="specs" className="grid gap-10 lg:grid-cols-[1fr_1.4fr]">
        <div>
          <Kicker>Reference build</Kicker>
          <h2 id="specs" className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">Key specifications</h2>
          <p className="mt-3 leading-relaxed text-slate-600">As documented for the open-source CubeRaman build, at roughly €750 in parts. These values describe that design, not a certified instrument.</p>
          <button className="mt-4 text-sm font-medium text-accent-600 hover:underline" onClick={onInstrument}>More on how the optics work →</button>
          <div role="note" className="mt-6 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm leading-relaxed text-amber-900">
            <p className="font-semibold">Laser safety</p>
            <p className="mt-1">The 532 nm module is a Class 3B laser and can cause permanent eye injury. Building or operating one requires certified 532 nm laser-safety eyewear and compliance with local regulations.</p>
          </div>
        </div>
        <dl className="divide-y divide-slate-100 rounded-2xl border border-slate-200 bg-white px-6">
          {SPECS.map(([k, val]) => (
            <div key={k} className="flex justify-between gap-6 py-3 text-sm"><dt className="text-slate-500">{k}</dt><dd className="text-right font-medium text-slate-900">{val}</dd></div>
          ))}
        </dl>
      </section>

      <section className="border-t border-slate-200 pt-6 text-xs leading-relaxed text-slate-500">
        Based on the open-source <a className="font-medium text-accent-600 hover:underline" href={REPO} target="_blank" rel="noreferrer">CubeRaman</a> project by Jacob Busshart.
        The 3D model is an original, simplified reconstruction of its published layout and parts. Optical spacings follow the listed components, while housing proportions are illustrative. No CubeRaman images, CAD files or code are reproduced.
      </section>
    </div>
  )
}
