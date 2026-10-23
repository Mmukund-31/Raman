import { lazy, Suspense, useEffect, useState } from 'react'
import { Analyze } from './pages/Analyze'
import { Home } from './pages/Home'

const Instrument = lazy(() => import('./pages/Instrument').then(m => ({ default: m.Instrument })))
const Diabetes = lazy(() => import('./pages/Diabetes').then(m => ({ default: m.Diabetes })))
const PAGES = [['home', 'Overview'], ['diabetes', 'Diabetes study'], ['analyze', 'Analyze'], ['instrument', 'Instrument']] as const
type Page = (typeof PAGES)[number][0]

function Logo() {
  return (
    <svg aria-hidden viewBox="0 0 36 36" className="h-9 w-9">
      <rect width="36" height="36" rx="10" fill="#157f54" />
      <path d="M6 25 L11 24 L13 12 L15 24 L19 21 L21.5 8 L24 23 L30 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="21.5" cy="8" r="2" fill="#b9e6cb" />
    </svg>
  )
}

export default function App() {
  // '#/diabetes' etc. makes each page linkable; in-page anchors such as '#cohort' are not pages and are ignored.
  const [page, setPage] = useState<Page>(() => PAGES.find(([id]) => window.location.hash === `#/${id}`)?.[0] ?? 'home')
  const [key, setKey] = useState(0) // remounting Analyze returns to a clean upload screen
  useEffect(() => {
    const sync = () => { const p = PAGES.find(([id]) => window.location.hash === `#/${id}`)?.[0]; if (p) setPage(p) }
    window.addEventListener('hashchange', sync)
    return () => window.removeEventListener('hashchange', sync)
  }, [])
  const open = (p: Page) => {
    if (p === 'analyze' && page === 'analyze') setKey(k => k + 1)
    setPage(p); window.history.replaceState(null, '', p === 'home' ? window.location.pathname : `#/${p}`); window.scrollTo({ top: 0 })
  }
  const loading = <p className="py-24 text-center text-sm text-slate-400">Loading…</p>
  return (
    <div className="flex min-h-screen flex-col bg-white">
      <div className="no-print bg-accent-900 text-[12px] text-accent-100">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-1.5 sm:px-6">
          <span>Open research platform · Raman spectroscopy for personalised healthcare</span>
          <span className="hidden sm:inline">Research use only · not a diagnostic device</span>
        </div>
      </div>
      <header className="no-print sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <button onClick={() => open('home')} className="flex items-center gap-3 text-left" aria-label="RamanReach home">
            <Logo />
            <span className="leading-tight">
              <span className="block text-[17px] font-semibold tracking-tight text-slate-900">RamanReach</span>
              <span className="block text-[11px] tracking-wide text-slate-500">Spectroscopy Research Lab</span>
            </span>
          </button>
          <nav aria-label="Main" className="flex items-center gap-0.5 overflow-x-auto text-sm">
            {PAGES.map(([id, label]) => (
              <button key={id} onClick={() => open(id)} aria-current={page === id ? 'page' : undefined}
                className={`relative rounded-lg px-3 py-2 font-medium whitespace-nowrap transition ${page === id ? 'text-accent-800' : 'text-slate-600 hover:bg-accent-50 hover:text-slate-900'}`}>
                {label}
                {page === id && <span aria-hidden className="absolute inset-x-3 -bottom-[13px] h-0.5 rounded-full bg-accent-600" />}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <main className="flex-1">
        {page === 'home' ? <Home onAnalyze={() => open('analyze')} onStudy={() => open('diabetes')} />
          : page === 'analyze' ? <div className="mx-auto max-w-7xl px-4 pb-16 sm:px-6"><Analyze key={key} /></div>
            : page === 'diabetes' ? <Suspense fallback={loading}><Diabetes onAnalyze={() => open('analyze')} /></Suspense>
              : <div className="mx-auto max-w-5xl px-4 pb-16 sm:px-6"><Suspense fallback={loading}><Instrument onAnalyze={() => open('analyze')} /></Suspense></div>}
      </main>

      <footer className="no-print border-t border-accent-100 bg-mint">
        <div className="mx-auto grid max-w-7xl gap-10 px-4 py-12 sm:px-6 lg:grid-cols-[2fr_1fr]">
          <div>
            <div className="flex items-center gap-3"><Logo /><span className="font-semibold text-slate-900">RamanReach</span></div>
            <p className="mt-3 text-sm leading-relaxed text-slate-600">Open-source software for Raman spectrum analysis, building reagent-free, personalised health monitoring. Study 1: diabetes and urine.</p>
          </div>
          <div>
            <p className="kicker">Platform</p>
            <ul className="mt-3 space-y-2 text-sm">
              {PAGES.map(([id, label]) => <li key={id}><button className="text-slate-600 hover:text-accent-800" onClick={() => open(id)}>{label}</button></li>)}
            </ul>
          </div>
        </div>
      </footer>
    </div>
  )
}
