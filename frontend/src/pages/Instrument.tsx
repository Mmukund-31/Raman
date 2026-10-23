import { lazy, Suspense, useEffect, useState } from 'react'
import { BEAMS, PARTS, PIPELINE, scatteredNm, SPECS, STEPS, type StepId } from '../instrument/model'

const CubeScene = lazy(() => import('../instrument/CubeScene').then(m => ({ default: m.CubeScene })))
const TOUR_MS = 7000

function Kicker({ children }: { children: string }) {
  return <p className="text-[11px] font-semibold tracking-[0.14em] text-accent-700 uppercase">{children}</p>
}

export function Instrument({ onAnalyze }: { onAnalyze: () => void }) {
  const [step, setStep] = useState<StepId | null>(null)
  const [exploded, setExploded] = useState(false)
  const [touring, setTouring] = useState(false)
  const i = step ? STEPS.findIndex(s => s.id === step) : -1
  const current = i >= 0 ? STEPS[i] : null
  const go = (k: number) => { setExploded(false); setStep(STEPS[(k + STEPS.length) % STEPS.length].id) }

  useEffect(() => {
    if (!touring) return
    const t = setTimeout(() => (i === STEPS.length - 1 ? (setTouring(false), setStep(null)) : go(i + 1)), i < 0 ? 0 : TOUR_MS)
    return () => clearTimeout(t)
  }, [touring, i])

  const select = (s: StepId) => { setTouring(false); setExploded(false); setStep(s) }
  const lo = scatteredNm(532, 600), hi = scatteredNm(532, 3000)

  return (
    <div className="space-y-16">
      <section className="mx-auto max-w-3xl pt-6 text-center sm:pt-10">
        <p className="inline-flex items-center gap-2 rounded-full border border-accent-100 bg-accent-50 px-3 py-1 text-xs font-medium text-accent-700">
          <span className="h-1.5 w-1.5 rounded-full bg-accent-500" /> The instrument
        </p>
        <h1 className="mt-5 text-4xl font-semibold tracking-tight text-balance text-slate-900 sm:text-5xl">How a 3D-printed Raman spectrometer works</h1>
        <p className="mx-auto mt-4 max-w-xl text-lg leading-relaxed text-pretty text-slate-500">
          Follow the light through a compact back-scattering probe, from a green laser to the spectrum RamanReach analyses.
        </p>
      </section>

      <section aria-label="Interactive model" className="card overflow-hidden">
        <div className="grid lg:grid-cols-[minmax(0,1fr)_380px]">
          <div className="relative h-[440px] bg-[radial-gradient(40rem_24rem_at_50%_40%,#ffffff,#eef2f8)] sm:h-[560px]">
            <Suspense fallback={<div className="flex h-full items-center justify-center text-sm text-slate-400">Loading 3D model…</div>}>
              <CubeScene step={step} exploded={exploded} onSelect={select} />
            </Suspense>
            <div className="pointer-events-none absolute inset-x-0 top-0 flex flex-wrap items-start justify-between gap-2 p-4">
              <ul className="pointer-events-auto space-y-1 rounded-xl border border-slate-200 bg-white/85 px-3 py-2 text-[11px] text-slate-600 backdrop-blur" aria-label="Legend">
                {BEAMS.slice(0, 2).map(b => <li key={b.id} className="flex items-center gap-2"><span className="h-1 w-4 rounded-full" style={{ background: b.colour }} />{b.label}</li>)}
              </ul>
              <div className="pointer-events-auto flex gap-1 rounded-xl border border-slate-200 bg-white/85 p-1 text-xs backdrop-blur">
                <button onClick={() => { setTouring(false); setStep(null) }} aria-pressed={!step && !exploded}
                  className={`rounded-lg px-2.5 py-1.5 font-medium ${!step && !exploded ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'}`}>Overview</button>
                <button onClick={() => { setTouring(false); setStep(null); setExploded(e => !e) }} aria-pressed={exploded}
                  className={`rounded-lg px-2.5 py-1.5 font-medium ${exploded ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'}`}>Exploded view</button>
              </div>
            </div>
            <p className="pointer-events-none absolute bottom-3 left-4 text-[11px] text-slate-400">Drag to rotate · scroll to zoom · click a label</p>
          </div>

          <aside className="flex flex-col border-t border-slate-200 lg:border-t-0 lg:border-l">
            <ol className="border-b border-slate-200 p-3" aria-label="Tour steps">
              {STEPS.map(s => (
                <li key={s.id}>
                  <button onClick={() => select(s.id)} aria-current={step === s.id ? 'step' : undefined}
                    className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm transition ${step === s.id ? 'bg-accent-50 text-accent-700' : 'text-slate-600 hover:bg-slate-50'}`}>
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
                    {PARTS.filter(p => p.step === current.id).map(p => (
                      <div key={p.id} className="flex justify-between gap-3 border-t border-slate-100 pt-2 text-xs">
                        <dt className="font-medium text-slate-700">{p.name}</dt><dd className="text-right text-slate-500">{p.spec}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
              ) : (
                <div className="flex-1">
                  <Kicker>Overview</Kicker>
                  <h2 className="mt-1 text-lg font-semibold tracking-tight text-slate-900">One cube, two light paths</h2>
                  <p className="mt-2 text-sm leading-relaxed text-slate-600">
                    The green excitation beam is turned down onto the sample. The far weaker Raman light travels back up, through the mirror and filters, into the spectrometer.
                    Take the tour, or select any step.
                  </p>
                </div>
              )}
              <div className="mt-6 flex items-center gap-2">
                {current ? (
                  <>
                    <button className="btn-ghost px-3" onClick={() => { setTouring(false); go(i - 1) }} aria-label="Previous step">←</button>
                    <button className="btn-ghost px-3" onClick={() => { setTouring(false); go(i + 1) }} aria-label="Next step">→</button>
                  </>
                ) : null}
                <button className="btn-primary ml-auto" onClick={() => (touring ? setTouring(false) : (setStep(null), setExploded(false), setTouring(true)))}>
                  {touring ? 'Pause tour' : current ? 'Play tour' : 'Start the tour'}
                </button>
              </div>
            </div>
          </aside>
        </div>
      </section>

      <section aria-label="The signal" className="grid gap-px overflow-hidden rounded-2xl border border-slate-200 bg-slate-200 sm:grid-cols-3">
        {[
          ['532 nm', 'Excitation wavelength', 'A single green laser line; every Raman band is measured as a shift from it.'],
          ['~1 in 10⁷', 'Photons Raman-scattered', 'Most light scatters unchanged, which is why two stages of filtering are needed.'],
          [`${lo.toFixed(0)}–${hi.toFixed(0)} nm`, 'Where 600–3000 cm⁻¹ appears', 'The fingerprint region maps onto this narrow band of scattered wavelengths.'],
        ].map(([v, l, d]) => (
          <div key={l} className="bg-white p-6">
            <p className="text-3xl font-semibold tracking-tight text-slate-900 tabular-nums">{v}</p>
            <p className="mt-1 text-sm font-medium text-slate-700">{l}</p>
            <p className="mt-2 text-sm leading-relaxed text-slate-500">{d}</p>
          </div>
        ))}
      </section>

      <section aria-labelledby="pipeline" className="grid gap-10 lg:grid-cols-[1fr_1.4fr]">
        <div>
          <Kicker>From detector to report</Kicker>
          <h2 id="pipeline" className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">What happens to the signal next</h2>
          <p className="mt-3 leading-relaxed text-slate-600">The spectrometer delivers raw counts per pixel. Software turns them into a clean, comparable spectrum, the same stages RamanReach applies to every upload.</p>
          <button className="btn-primary mt-6" onClick={onAnalyze}>Analyze a spectrum</button>
        </div>
        <ol className="grid gap-3 sm:grid-cols-2">
          {PIPELINE.map(([t, d], k) => (
            <li key={t} className="rounded-xl border border-slate-200 bg-white p-4">
              <p className="text-xs font-semibold text-accent-600 tabular-nums">0{k + 1}</p>
              <p className="mt-1 font-medium text-slate-900">{t}</p>
              <p className="mt-1 text-sm leading-relaxed text-slate-500">{d}</p>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="specs" className="grid gap-10 lg:grid-cols-[1fr_1.4fr]">
        <div>
          <Kicker>Reference build</Kicker>
          <h2 id="specs" className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">Key specifications</h2>
          <p className="mt-3 leading-relaxed text-slate-600">As documented for the open-source CubeRaman build. Values describe that design, not a certified instrument.</p>
          <div role="note" className="mt-6 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm leading-relaxed text-amber-900">
            <p className="font-semibold">Laser safety</p>
            <p className="mt-1">The 532 nm module is a Class 3B laser and can cause permanent eye injury. Building or operating such a device requires certified laser-safety eyewear and compliance with local regulations.</p>
          </div>
        </div>
        <dl className="divide-y divide-slate-100 rounded-2xl border border-slate-200 bg-white px-6">
          {SPECS.map(([k, val]) => (
            <div key={k} className="flex justify-between gap-6 py-3 text-sm"><dt className="text-slate-500">{k}</dt><dd className="text-right font-medium text-slate-900">{val}</dd></div>
          ))}
        </dl>
      </section>
    </div>
  )
}
