import { lazy, Suspense, useState } from 'react'
import { Analyze } from './pages/Analyze'
import { Home } from './pages/Home'

const Instrument = lazy(() => import('./pages/Instrument').then(m => ({ default: m.Instrument })))
const PAGES = [['home', 'Home'], ['analyze', 'Analyze'], ['instrument', 'How it works']] as const
type Page = (typeof PAGES)[number][0]

export default function App() {
  const [page, setPage] = useState<Page>('home')
  const [key, setKey] = useState(0) // remounting Analyze returns to a clean upload screen
  const open = (p: Page) => { if (p === 'analyze' && page === 'analyze') setKey(k => k + 1); setPage(p); window.scrollTo({ top: 0 }) }
  return (
    <div className="min-h-screen bg-[radial-gradient(60rem_30rem_at_50%_-10rem,rgba(59,110,245,0.10),transparent)]">
      <header className="no-print">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-5 sm:px-6">
          <button onClick={() => open('home')} className="flex items-center gap-2.5" aria-label="RamanReach home">
            <svg aria-hidden viewBox="0 0 32 32" className="h-8 w-8"><rect width="32" height="32" rx="9" fill="#2856e0" /><path d="M5 22 L10 21 L12 10 L14 21 L18 18 L20 7 L22 20 L27 21" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
            <span className="text-[17px] font-semibold tracking-tight">RamanReach</span>
          </button>
          <nav aria-label="Main" className="flex gap-1 rounded-xl border border-slate-200 bg-white/70 p-1 text-sm backdrop-blur">
            {PAGES.map(([id, label]) => (
              <button key={id} onClick={() => open(id)} aria-current={page === id ? 'page' : undefined}
                className={`rounded-lg px-3 py-1.5 font-medium transition ${page === id ? 'bg-slate-900 text-white' : 'text-slate-600 hover:text-slate-900'}`}>{label}</button>
            ))}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 pb-16 sm:px-6">
        {page === 'home' ? <Home onAnalyze={() => open('analyze')} onInstrument={() => open('instrument')} /> : page === 'analyze' ? <Analyze key={key} /> : (
          <Suspense fallback={<p className="py-24 text-center text-sm text-slate-400">Loading…</p>}>
            <Instrument onAnalyze={() => open('analyze')} />
          </Suspense>
        )}
      </main>
      <footer className="no-print mx-auto max-w-5xl px-4 pb-10 text-center text-xs text-slate-400 sm:px-6">
        RamanReach is experimental research software and is not intended for diagnostic or safety decisions.
      </footer>
    </div>
  )
}
