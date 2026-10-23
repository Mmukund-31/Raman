import type { ReactNode } from 'react'
import type { StageState } from '../services/progress'
import type { StageStatus } from '../types/report'

// Decorative only: a smooth band shape, not data.
const WAVE = (() => {
  const bands = [[0.12, 0.35, 0.025], [0.28, 0.9, 0.012], [0.36, 0.45, 0.02], [0.52, 0.7, 0.015], [0.61, 0.3, 0.03], [0.78, 0.55, 0.012], [0.88, 0.25, 0.02]]
  const pts = Array.from({ length: 141 }, (_, i) => {
    const t = i / 140
    const y = bands.reduce((s, [c, a, w]) => s + a * w * w / ((t - c) ** 2 + w * w), 0.04 * Math.sin(t * 9))
    return `${(20 + t * 560).toFixed(1)},${(150 - y * 110).toFixed(1)}`
  })
  return `M${pts.join(' L')}`
})()

function Visual({ failed }: { failed: boolean }) {
  const stroke = failed ? '#f43f5e' : '#2856e0'
  return (
    <svg viewBox="0 0 600 180" className="w-full" aria-hidden>
      <defs>
        <linearGradient id="fill" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor={stroke} stopOpacity=".18" /><stop offset="1" stopColor={stroke} stopOpacity="0" /></linearGradient>
        <linearGradient id="scan" x1="0" x2="1"><stop offset="0" stopColor={stroke} stopOpacity="0" /><stop offset=".5" stopColor={stroke} stopOpacity=".35" /><stop offset="1" stopColor={stroke} stopOpacity="0" /></linearGradient>
      </defs>
      {[40, 80, 120].map(y => <line key={y} x1="20" x2="580" y1={y} y2={y} stroke="#e2e8f0" strokeDasharray="2 6" />)}
      <line x1="20" x2="580" y1="155" y2="155" stroke="#cbd5e1" />
      <path d={`${WAVE} L580,155 L20,155 Z`} fill="url(#fill)" />
      <path d={WAVE} pathLength={1} className={failed ? '' : 'wave-path'} fill="none" stroke={stroke} strokeWidth="2.2" strokeLinejoin="round" strokeLinecap="round" />
      {!failed && <g className="scan-line"><rect x="4" y="12" width="32" height="143" fill="url(#scan)" /><line x1="20" x2="20" y1="12" y2="155" stroke={stroke} strokeOpacity=".6" /></g>}
      {!failed && [70, 160, 250, 330, 420, 510].map((x, i) => (
        <circle key={x} cx={x} cy={140} r={i % 2 ? 2 : 1.5} fill={stroke} className="particle" style={{ animationDelay: `${i * 0.45}s` }} />
      ))}
    </svg>
  )
}

const ICON: Record<StageStatus, string> = { pending: '', running: '', done: '✓', skipped: '–', error: '!' }

export function AnalysisLoader({ name, stages, error, onRetry, onCancel, onBack, children }: {
  name: string; stages: StageState[]; error?: string; onRetry?: () => void; onCancel?: () => void; onBack?: () => void; children?: ReactNode
}) {
  const finished = stages.filter(s => s.status === 'done' || s.status === 'skipped' || s.status === 'error').length
  const failed = !!error
  return (
    <section className="card mx-auto max-w-2xl overflow-hidden fade-up" aria-labelledby="loader-title">
      <div className="bg-gradient-to-b from-accent-50/70 to-white px-6 pt-6 sm:px-10"><Visual failed={failed} /></div>
      <div className="px-6 pb-8 sm:px-10">
        <h2 id="loader-title" className="text-xl font-semibold tracking-tight text-slate-900">
          {failed ? 'The analysis could not finish' : 'Analyzing your spectrum…'}
        </h2>
        <p className="mt-1 truncate text-sm text-slate-500">{name}</p>

        <div className="mt-5" aria-hidden={failed}>
          <div className="flex justify-between text-xs text-slate-500"><span>{finished} of {stages.length} steps finished</span></div>
          <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-slate-100" role="progressbar" aria-label="Analysis steps finished"
            aria-valuemin={0} aria-valuemax={stages.length} aria-valuenow={finished}>
            <div className={`h-full rounded-full transition-all duration-500 ${failed ? 'bg-rose-400' : 'bg-accent-600'}`} style={{ width: `${(100 * finished) / stages.length}%` }} />
          </div>
        </div>

        <ol className="mt-6 space-y-2.5" aria-live="polite">
          {stages.map(s => (
            <li key={s.id} data-status={s.status} className="flex items-center gap-3 text-sm">
              <span aria-hidden className={`flex h-6 w-6 flex-none items-center justify-center rounded-full text-xs font-semibold ${
                s.status === 'done' ? 'bg-emerald-100 text-emerald-700'
                  : s.status === 'skipped' ? 'bg-slate-100 text-slate-500'
                    : s.status === 'error' ? 'bg-rose-100 text-rose-700'
                      : s.status === 'running' ? 'border-2 border-accent-200 border-t-accent-600 motion-safe:animate-spin'
                        : 'border border-slate-200'}`}>{ICON[s.status]}</span>
              <span className={s.status === 'pending' ? 'text-slate-400' : s.status === 'running' ? 'font-medium text-slate-900' : 'text-slate-700'}>
                {s.label}
                <span className="sr-only"> — {s.status === 'skipped' ? 'skipped: not enough data' : s.status}</span>
                {s.status === 'skipped' && <span className="ml-2 text-xs text-slate-400">not enough data</span>}
                {s.status === 'done' && s.detail && <span className="ml-2 text-xs text-slate-400">{s.detail}</span>}
              </span>
            </li>
          ))}
        </ol>

        {failed ? (
          <div className="mt-6">
            <div role="alert" className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-900">{error}</div>
            {children}
            <div className="mt-4 flex flex-wrap gap-2">
              {onRetry && <button className="btn-primary" onClick={onRetry}>Try again</button>}
              {onBack && <button className="btn-ghost" onClick={onBack}>Choose another file</button>}
            </div>
          </div>
        ) : onCancel && <button className="btn-ghost mt-6" onClick={onCancel}>Cancel</button>}
      </div>
    </section>
  )
}
