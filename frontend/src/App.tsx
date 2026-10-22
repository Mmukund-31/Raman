import { useState } from 'react'
import { Analyze } from './pages/Analyze'
import { About, Home } from './pages/Info'

const tabs = ['Home', 'Analyze', 'Methodology'] as const

export default function App() {
  const [tab, setTab] = useState<(typeof tabs)[number]>('Home')
  return (
    <div className="mx-auto max-w-6xl px-4 py-4">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-2 border-b pb-3">
        <h1 className="text-2xl font-bold">RamanReach</h1>
        <nav className="flex gap-2" aria-label="Main">
          {tabs.map(t => (
            <button key={t} onClick={() => setTab(t)} aria-current={tab === t ? 'page' : undefined}
              className={`rounded px-3 py-1 ${tab === t ? 'bg-blue-700 text-white' : 'hover:bg-slate-200'}`}>{t}</button>
          ))}
        </nav>
      </header>
      <main>
        {tab === 'Home' && <Home go={() => setTab('Analyze')} />}
        {tab === 'Analyze' && <Analyze />}
        {tab === 'Methodology' && <About />}
      </main>
      <footer className="mt-8 border-t pt-3 text-xs text-slate-600">Experimental, non-diagnostic research prototype. Bundled spectra are synthetic.</footer>
    </div>
  )
}
