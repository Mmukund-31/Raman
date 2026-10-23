import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import type { Data, Shape } from 'plotly.js'
import { Figure } from '../components/report/Figure'
import { Figure3D, FigurePair } from '../components/report/Figure3D'
import { curtain } from '../components/report/ribbons'
import { SEQUENTIAL } from '../components/theme'
import { PROGRAMME, STATUS_STYLE } from '../content/programme'
import { analyzeUrine, getParticipant, getUrineExamples, getUrineStudy, urineExampleUrl } from '../services/urine'
import type { IndexKey, TrialData, UrineDatasetId, UrineExample, UrineParticipant, UrineResult, UrineStudy } from '../types/urine'

// Categorical slots 1-3 of the validated dataviz palette; colour follows the cohort, never its rank.
const BLUE = '#2a78d6', ORANGE = '#eb6834', AQUA = '#1baf7a'
const GROUP_COLOR: Record<string, string> = { control: BLUE, healthy: BLUE, diabetes: ORANGE, diabetic: ORANGE, non_diabetic_ckd: AQUA }
const COHORT_COLOR: Record<string, string> = { control: BLUE, responder: AQUA, 'non-responder': ORANGE }
const color = (g: string) => GROUP_COLOR[g] ?? '#52514e'
const GLUCOSE_BANDS = [1060, 1125]
const INDEX_KEYS: IndexKey[] = ['glucose', 'ketones', 'urea']
const fmt = (v: number | null | undefined, d = 2) => (v == null || !Number.isFinite(v) ? '—' : v.toFixed(d))
const pct = (v: number) => `${Math.round(v * 100)}%`

const DATASETS: { id: UrineDatasetId; label: string; sub: string }[] = [
  { id: 'trial', label: 'Monitoring trial', sub: 'Simulated · 70 participants · 12 weeks' },
  { id: 'zenodo', label: 'Patient urine', sub: 'Measured · Zenodo 7343559 · 250 spectra' },
]

function bandShapes(): Partial<Shape>[] {
  return GLUCOSE_BANDS.map(c => ({ type: 'rect', xref: 'x', yref: 'paper', x0: c - 12, x1: c + 12, y0: 0, y1: 1, fillcolor: 'rgba(21,127,84,0.08)', line: { width: 0 }, layer: 'below' }))
}
const bandNotes = [{ x: (GLUCOSE_BANDS[0] + GLUCOSE_BANDS[1]) / 2, y: 1.02, yref: 'paper' as const, text: 'glucose bands', showarrow: false, font: { size: 10, color: '#0f6644' } }]

function Section({ id, n, title, lede, children }: { id: string; n: string; title: string; lede: ReactNode; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-h`} className="scroll-mt-32 border-t border-slate-200 py-14 first:border-t-0">
      <div className="mb-7 grid gap-3 lg:grid-cols-[220px_1fr]">
        <p className="kicker pt-2">{n}</p>
        <div>
          <h2 id={`${id}-h`} className="section-title">{title}</h2>
          <div className="mt-3 max-w-3xl leading-relaxed text-slate-600">{lede}</div>
        </div>
      </div>
      {children}
    </section>
  )
}

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
      <p className="text-xs text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold tracking-tight text-slate-900 tabular-nums">{value}</p>
      {note && <p className="mt-0.5 text-[11px] text-slate-400">{note}</p>}
    </div>
  )
}

// ------------------------------------------------------------------------------------------- 1. cohort spectra
function CohortSpectra({ s }: { s: UrineStudy }) {
  const x = s.grid
  const two: Data[] = s.mean_spectra.flatMap(m => [
    { x: [...x, ...[...x].reverse()], y: [...m.mean.map((v, i) => v + m.sd[i]), ...m.mean.map((v, i) => v - m.sd[i]).reverse()], type: 'scatter', mode: 'lines',
      fill: 'toself', fillcolor: `${color(m.group)}1f`, line: { width: 0 }, hoverinfo: 'skip', showlegend: false, legendgroup: m.group } as Data,
    { x, y: m.mean, type: 'scatter', mode: 'lines', name: `${m.label} (n=${m.n})`, legendgroup: m.group, line: { color: color(m.group), width: 2 },
      hovertemplate: `${m.label}<br>%{x:.0f} cm⁻¹ · %{y:.4f}<extra></extra>` } as Data,
  ])
  const seen = new Set<string>()
  const groupIdx = new Map(s.groups.map((g, i) => [g.id, i]))
  const three: Data[] = s.waterfall.flatMap((w, k) => {
    const first = !seen.has(w.group); seen.add(w.group)
    return curtain(x, w.y, k + 2 * (groupIdx.get(w.group) ?? 0), color(w.group), s.groups.find(g => g.id === w.group)?.label ?? w.group, {
      legendgroup: w.group, showlegend: first, fill: 0.55,
      hover: `${w.sample_id}<br>glucose index ${fmt(w.glucose_index)}<br>%{x:.0f} cm⁻¹ · %{z:.4f}<extra></extra>`,
    })
  })
  return (
    <>
      <FigurePair
        two={<Figure data={two} height={360} label="Mean urine spectrum per cohort with ±1 SD band" xTitle="Raman shift (cm⁻¹)" yTitle="Normalised intensity"
          layout={{ shapes: bandShapes(), annotations: bandNotes, legend: { orientation: 'h', y: 1.16, x: 0 }, margin: { t: 40, r: 16, l: 64, b: 52 } }} />}
        three={<Figure3D data={three} height={380} label="Individual urine spectra as a 3D waterfall, ordered by cohort and glucose index"
          xTitle="Raman shift (cm⁻¹)" yTitle="Spectrum (by cohort, glucose ↑)" zTitle="Intensity" aspect={{ x: 2.2, y: 1.3, z: 0.7 }} />}
        note={<>Left: cohort means with a ±1 SD band; green columns mark the glucose bands at 1060 and 1125 cm⁻¹. Right: individual baseline spectra (up to 12 per cohort, spanning the range of the glucose index) stacked front to back.</>} />
      <div className="mt-4 rounded-xl border border-slate-200 bg-white p-3">
        <p className="px-2 pt-1 text-sm font-medium text-slate-800">Difference spectrum · {s.difference.label}</p>
        <Figure data={[{ x, y: s.difference.y, type: 'scatter', mode: 'lines', name: 'Difference', line: { color: '#52514e', width: 1.6 }, hovertemplate: '%{x:.0f} cm⁻¹ · %{y:.4f}<extra></extra>' } as Data]}
          height={220} label="Difference between the diabetic and reference mean spectra" xTitle="Raman shift (cm⁻¹)" yTitle="Δ intensity"
          layout={{ shapes: [...bandShapes(), { type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 0, y1: 0, line: { color: '#94a3b8', width: 1 } }], annotations: bandNotes, margin: { t: 24, r: 16, l: 64, b: 48 } }} />
      </div>
    </>
  )
}

// ------------------------------------------------------------------------------------------- 2. biomarker indices
function Biomarkers({ s }: { s: UrineStudy }) {
  const [key, setKey] = useState<IndexKey>('glucose')
  const jitter = (i: number) => ((Math.sin(i * 12.9898) * 43758.5453) % 1) * 0.28
  const two: Data[] = s.groups.map((g, k) => {
    const vals = s.index_stats[key][g.id]?.values ?? []
    return { type: 'scatter', mode: 'markers', name: g.label, x: vals.map((_, i) => k + jitter(i)), y: vals,
      marker: { color: color(g.id), size: 8, opacity: 0.6, line: { color: '#fff', width: 1 } }, hovertemplate: `${g.label}<br>${s.indices[key].label} %{y:.3f}<extra></extra>` } as Data
  })
  const medians: Partial<Shape>[] = s.groups.flatMap((g, k) => {
    const st = s.index_stats[key][g.id]
    return st ? [{ type: 'line', x0: k - 0.38, x1: k + 0.38, y0: st.median, y1: st.median, line: { color: '#0f172a', width: 2 } },
      { type: 'rect', x0: k - 0.38, x1: k + 0.38, y0: st.q1, y1: st.q3, line: { color: '#475569', width: 1 }, fillcolor: 'rgba(0,0,0,0)' }] : []
  })
  const three: Data[] = s.groups.map(g => {
    const pts = s.samples.filter(p => p.group === g.id && (p.week == null || p.week === 0))
    return { type: 'scatter3d', mode: 'markers', name: g.label, x: pts.map(p => p.indices.glucose), y: pts.map(p => p.indices.ketones), z: pts.map(p => p.indices.urea),
      text: pts.map(p => p.sample_id), marker: { color: color(g.id), size: 4, opacity: 0.85, line: { color: '#fff', width: 0.5 } },
      hovertemplate: '%{text}<br>glucose %{x:.3f} · ketones %{y:.3f} · urea %{z:.2f}<extra></extra>' } as Data
  })
  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-2" role="radiogroup" aria-label="Band index">
        {INDEX_KEYS.map(k => (
          <button key={k} role="radio" aria-checked={key === k} onClick={() => setKey(k)}
            className={`rounded-full border px-3 py-1 text-sm transition ${key === k ? 'border-accent-600 bg-accent-600 text-white' : 'border-slate-300 bg-white text-slate-700 hover:border-accent-400'}`}>{s.indices[k].label}</button>
        ))}
        <span className="text-xs text-slate-500">{s.indices[key].note}</span>
      </div>
      <FigurePair
        two={<Figure data={two} height={360} label={`${s.indices[key].label} per cohort (points, median line and interquartile box)`} xTitle="" yTitle={s.indices[key].label}
          layout={{ shapes: medians, xaxis: { tickvals: s.groups.map((_, k) => k), ticktext: s.groups.map(g => g.label), gridcolor: '#eef2f7', tickfont: { size: 11, color: '#334155' } }, legend: { orientation: 'h', y: 1.12, x: 0 }, margin: { t: 36, r: 16, l: 64, b: 40 } }} />}
        three={<Figure3D data={three} height={380} label="Glucose, ketone and urea indices for every baseline sample" xTitle="Glucose index" yTitle="Ketone index" zTitle="Urea index" aspect={{ x: 1.4, y: 1.2, z: 0.9 }} />}
        note="Each index is a band height divided by the creatinine band at 680 cm⁻¹, which cancels most of the dilution difference between spot urine samples. The box marks the interquartile range; the dark line is the median." />
      <div className="mt-6 overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="w-full min-w-[560px] text-sm">
          <caption className="px-4 pt-3 pb-1 text-left text-sm font-medium text-slate-800">Urine Raman bands used in this study (approximate literature assignments)</caption>
          <thead><tr className="border-b border-slate-200 text-left text-xs text-slate-500"><th className="px-4 py-2 font-medium">Position (cm⁻¹)</th><th className="px-4 py-2 font-medium">Assignment</th><th className="px-4 py-2 font-medium">Molecule</th><th className="px-4 py-2 font-medium">Role</th></tr></thead>
          <tbody>
            {s.bands.map(b => (
              <tr key={b.position} className="border-b border-slate-100 last:border-0">
                <td className="px-4 py-1.5 font-mono text-[13px] tabular-nums">{b.position}</td><td className="px-4 py-1.5">{b.label}</td>
                <td className="px-4 py-1.5 text-slate-600">{b.solute.replace('_', ' ')}</td>
                <td className="px-4 py-1.5 text-slate-500">{b.solute === 'glucose' ? 'Glycosuria marker' : b.solute === 'ketones' ? 'Ketonuria marker' : b.position === 680 ? 'Dilution reference' : b.solute === 'albumin' ? 'Proteinuria (context)' : 'Matrix / context'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

// ------------------------------------------------------------------------------------------- 3. PCA
function Pca({ s }: { s: UrineStudy }) {
  const ev = s.pca.explained_variance_ratio
  const pts = (g: string) => s.samples.filter(p => p.group === g && (p.week == null || p.week === 0))
  const two: Data[] = s.groups.map(g => ({ type: 'scatter', mode: 'markers', name: g.label, x: pts(g.id).map(p => p.pc[0]), y: pts(g.id).map(p => p.pc[1]), text: pts(g.id).map(p => p.sample_id),
    marker: { color: color(g.id), size: 8, opacity: 0.75, line: { color: '#fff', width: 1 } }, hovertemplate: '%{text}<br>PC1 %{x:.3f} · PC2 %{y:.3f}<extra></extra>' } as Data))
  const three: Data[] = s.groups.map(g => ({ type: 'scatter3d', mode: 'markers', name: g.label, x: pts(g.id).map(p => p.pc[0]), y: pts(g.id).map(p => p.pc[1]), z: pts(g.id).map(p => p.pc[2]),
    text: pts(g.id).map(p => p.sample_id), marker: { color: color(g.id), size: 4, opacity: 0.85, line: { color: '#fff', width: 0.5 } }, hovertemplate: '%{text}<br>PC1 %{x:.3f} · PC2 %{y:.3f} · PC3 %{z:.3f}<extra></extra>' } as Data))
  const loadings: Data[] = s.pca.loadings.slice(0, 2).map((l, k) => ({ type: 'scatter', mode: 'lines', name: `PC${k + 1} loading`, x: s.grid, y: l, line: { color: k ? '#898781' : '#0f6644', width: 1.8, dash: k ? 'dot' : 'solid' }, hovertemplate: `PC${k + 1}<br>%{x:.0f} cm⁻¹ · %{y:.3f}<extra></extra>` } as Data))
  const ax = (k: number) => `PC${k + 1} (${pct(ev[k])} of variance)`
  return (
    <>
      <FigurePair
        two={<Figure data={two} height={360} label="PCA scores, PC1 against PC2" xTitle={ax(0)} yTitle={ax(1)} layout={{ legend: { orientation: 'h', y: 1.12, x: 0 }, margin: { t: 36, r: 16, l: 64, b: 52 } }} />}
        three={<Figure3D data={three} height={380} label="PCA scores in three dimensions, PC1 to PC3" xTitle={ax(0)} yTitle={ax(1)} zTitle={ax(2)} aspect={{ x: 1.3, y: 1.2, z: 1 }} />}
        note={<>The first three components hold {pct(ev.slice(0, 3).reduce((a, b) => a + b, 0))} of the spectral variance. PCA is unsupervised: separation shows where the variance lies, not that a classifier will separate the cohorts.</>} />
      <div className="mt-4 rounded-xl border border-slate-200 bg-white p-3">
        <p className="px-2 pt-1 text-sm font-medium text-slate-800">Loadings · which wavenumbers drive PC1 and PC2</p>
        <Figure data={loadings} height={240} label="PCA loadings for PC1 and PC2" xTitle="Raman shift (cm⁻¹)" yTitle="Loading"
          layout={{ shapes: bandShapes(), annotations: bandNotes, legend: { orientation: 'h', y: 1.2, x: 0 }, margin: { t: 32, r: 16, l: 64, b: 48 } }} />
      </div>
    </>
  )
}

// ------------------------------------------------------------------------------------------- 4. classification
function Classification({ s }: { s: UrineStudy }) {
  const c = s.classification
  const pos = s.groups.find(g => g.id === c.positive)?.label ?? c.positive
  const roc: Data[] = [
    { type: 'scatter', mode: 'lines', name: 'Chance', x: [0, 1], y: [0, 1], line: { color: '#94a3b8', dash: 'dash', width: 1.2 }, hoverinfo: 'skip' } as Data,
    { type: 'scatter', mode: 'lines', name: `Cross-validated ROC (AUC ${c.auc.toFixed(2)})`, x: c.roc.fpr, y: c.roc.tpr, line: { color: '#0f6644', width: 2, shape: 'hv' },
      fill: 'tozeroy', fillcolor: 'rgba(21,127,84,0.08)', hovertemplate: 'FPR %{x:.2f} · TPR %{y:.2f}<extra></extra>' } as Data,
  ]
  const scored = s.samples.filter(p => p.cv_probability != null)
  const three: Data[] = s.groups.map(g => {
    const pts = scored.filter(p => p.group === g.id)
    return { type: 'scatter3d', mode: 'markers', name: g.label, x: pts.map(p => p.pc[0]), y: pts.map(p => p.pc[1]), z: pts.map(p => p.cv_probability), text: pts.map(p => p.sample_id),
      marker: { color: color(g.id), size: 4, opacity: 0.85, line: { color: '#fff', width: 0.5 } }, hovertemplate: `%{text}<br>out-of-fold similarity to ${pos}: %{z:.2f}<extra></extra>` } as Data
  })
  const t = c.confusion
  return (
    <>
      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="ROC AUC" value={c.auc.toFixed(2)} note="0.5 = chance, 1 = perfect" />
        <Stat label="Sensitivity" value={pct(c.sensitivity)} note={`${pos} correctly flagged`} />
        <Stat label="Specificity" value={pct(c.specificity)} note="Others correctly not flagged" />
        <Stat label="Accuracy" value={pct(c.accuracy)} note={`${c.n} samples, ${c.n_folds}-fold CV`} />
      </div>
      <FigurePair
        two={<Figure data={roc} height={360} label="Receiver operating characteristic curve from cross-validation" xTitle="False-positive rate (1 − specificity)" yTitle="True-positive rate (sensitivity)"
          layout={{ xaxis: { range: [0, 1], gridcolor: '#eef2f7', constrain: 'domain' }, yaxis: { range: [0, 1.02], gridcolor: '#eef2f7', scaleanchor: 'x' }, legend: { orientation: 'h', y: -0.25, x: 0 }, margin: { t: 16, r: 16, l: 64, b: 72 } }} />}
        three={<Figure3D data={three} height={380} label="PCA position against the cross-validated cohort-similarity score" xTitle="PC1" yTitle="PC2" zTitle={`Similarity to ${pos}`} aspect={{ x: 1.3, y: 1.2, z: 1 }} />} />
      <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,320px)_1fr]">
        <table className="w-full overflow-hidden rounded-xl border border-slate-200 bg-white text-sm" aria-label="Confusion matrix at threshold 0.5">
          <thead><tr className="bg-slate-50 text-xs text-slate-500"><th className="p-2 text-left font-medium">Actual \ predicted</th><th className="p-2 font-medium">{pos}</th><th className="p-2 font-medium">Other</th></tr></thead>
          <tbody className="tabular-nums">
            <tr className="border-t border-slate-100"><th className="p-2 text-left font-medium text-slate-700">{pos}</th><td className="bg-accent-50 p-2 text-center font-semibold">{t.tp}</td><td className="p-2 text-center">{t.fn}</td></tr>
            <tr className="border-t border-slate-100"><th className="p-2 text-left font-medium text-slate-700">Other</th><td className="p-2 text-center">{t.fp}</td><td className="bg-accent-50 p-2 text-center font-semibold">{t.tn}</td></tr>
          </tbody>
        </table>
        <div className="text-sm leading-relaxed text-slate-600">
          <p><b className="font-medium text-slate-800">Method.</b> {c.method} Every score shown is out-of-fold: the sample was not used to fit the model that scored it.</p>
          {s.dataset.category === 'synthetic'
            ? <p className="mt-2">On simulated data the cohorts differ only by the solutes we put in, so near-perfect separation is expected. It shows that the pipeline works; it is not evidence of clinical accuracy.</p>
            : <p className="mt-2">This is the honest held-out result on real patient urine. Everyone in the comparison has kidney disease or is a healthy volunteer, so diabetes is not the only difference between the groups. Medication, diet and collection conditions also vary.</p>}
        </div>
      </div>
    </>
  )
}

// ------------------------------------------------------------------------------------------- 5. trial follow-up
function Trial({ t, grid }: { t: TrialData; grid: number[] }) {
  const weeks = t.weeks
  const lines: Data[] = [
    ...t.participants.map(p => ({ type: 'scatter', mode: 'lines', x: weeks, y: p.glucose_index, showlegend: false, hoverinfo: 'skip',
      line: { color: COHORT_COLOR[p.arm === 'control' ? 'control' : p.response], width: 1 }, opacity: 0.18 } as Data)),
    ...t.cohort_means.map(m => ({ type: 'scatter', mode: 'lines+markers', name: `${m.label} (n=${m.n})`, x: weeks, y: m.mean,
      error_y: { type: 'data', array: m.se, visible: true, color: COHORT_COLOR[m.cohort], thickness: 1.2, width: 4 },
      line: { color: COHORT_COLOR[m.cohort], width: 2.5 }, marker: { size: 8, color: COHORT_COLOR[m.cohort], line: { color: '#fff', width: 1.5 } },
      hovertemplate: `${m.label}<br>week %{x} · mean %{y:.3f}<extra></extra>` } as Data)),
  ]
  const surface: Data[] = [{ type: 'surface', x: grid, y: t.responder_surface.weeks, z: t.responder_surface.z, colorscale: SEQUENTIAL, showscale: false,
    contours: { x: { show: false }, y: { show: true, color: '#ffffff', width: 1 }, z: { show: false } } as never, hovertemplate: 'week %{y} · %{x:.0f} cm⁻¹ · %{z:.4f}<extra></extra>' } as Data]
  const order = [...t.participants].sort((a, b) => (a.arm === b.arm ? (a.response < b.response ? -1 : 1) : a.arm === 'control' ? -1 : 1))
  const seen = new Set<string>()
  const ribbons: Data[] = order.map((p, k) => {
    const cohort = p.arm === 'control' ? 'control' : p.response
    const first = !seen.has(cohort); seen.add(cohort)
    return { type: 'scatter3d', mode: 'lines+markers', x: weeks, y: weeks.map(() => k), z: p.glucose_index, name: t.cohort_means.find(m => m.cohort === cohort)?.label,
      legendgroup: cohort, showlegend: first, line: { color: COHORT_COLOR[cohort], width: 3 }, marker: { size: 2.5, color: COHORT_COLOR[cohort] },
      hovertemplate: `${p.participant}<br>week %{x} · glucose index %{z:.3f}<extra></extra>` } as Data
  })
  const cal = t.calibration
  const all = t.participants.flatMap(p => p.reference_glucose.map((g, i) => ({ g, v: p.glucose_index[i], c: p.arm === 'control' ? 'control' : p.response })))
  const calData: Data[] = (['control', 'responder', 'non-responder'] as const).map(c => ({ type: 'scatter', mode: 'markers', name: t.cohort_means.find(m => m.cohort === c)?.label,
    x: all.filter(a => a.c === c).map(a => a.g), y: all.filter(a => a.c === c).map(a => a.v), marker: { color: COHORT_COLOR[c], size: 7, opacity: 0.7, line: { color: '#fff', width: 1 } },
    hovertemplate: 'reference %{x:.0f} mg/dL · index %{y:.3f}<extra></extra>' } as Data))
  if (cal) {
    const xmax = Math.max(...all.map(a => a.g))
    calData.push({ type: 'scatter', mode: 'lines', name: `Linear fit (r = ${cal.r.toFixed(2)})`, x: [0, xmax], y: [cal.intercept, cal.intercept + cal.slope * xmax], line: { color: '#0f172a', width: 1.5, dash: 'dash' }, hoverinfo: 'skip' } as Data)
  }
  return (
    <>
      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Participants" value={String(t.participants.length)} note={`${weeks.length} visits · weeks ${weeks.join(', ')}`} />
        <Stat label="Responders' median fall" value={t.responder_median_drop != null ? pct(t.responder_median_drop) : '—'} note="Glucose index, week 0 → 12" />
        <Stat label="Raman vs reference glucose" value={cal ? `r = ${cal.r.toFixed(2)}` : '—'} note={cal ? `R² ${cal.r2.toFixed(2)} · ${cal.n} spectra` : undefined} />
        <Stat label="Responders" value={String(t.cohort_means.find(m => m.cohort === 'responder')?.n ?? 0)} note={`of ${t.participants.filter(p => p.arm !== 'control').length} with diabetes`} />
      </div>
      <FigurePair
        two={<Figure data={lines} height={380} label="Glucose index over the 12-week follow-up, cohort means with standard error and individual participants" xTitle="Week of follow-up" yTitle="Glucose index (/ creatinine)"
          layout={{ xaxis: { tickvals: weeks, gridcolor: '#eef2f7' }, legend: { orientation: 'h', y: 1.14, x: 0 }, margin: { t: 40, r: 16, l: 64, b: 52 } }} />}
        three={<Figure3D data={ribbons} height={400} label="Every participant's glucose index trajectory as a 3D ribbon" xTitle="Week" yTitle="Participant" zTitle="Glucose index" aspect={{ x: 1.1, y: 2, z: 0.8 }} camera={{ x: 1.9, y: -1.2, z: 0.8 }} />}
        note="Faint lines are individual participants; bold lines are cohort means ± standard error. Responders' glycosuria falls within weeks, while non-responders stay high." />
      <div className="mt-6">
        <FigurePair
          two={<Figure data={calData} height={360} label="Raman glucose index against the reference urinary glucose" xTitle="Reference urinary glucose (mg/dL)" yTitle="Raman glucose index"
            layout={{ legend: { orientation: 'h', y: 1.16, x: 0 }, margin: { t: 40, r: 16, l: 64, b: 52 } }} />}
          three={<Figure3D data={surface} height={380} label="Responders' mean urine spectrum at each visit as a 3D surface" xTitle="Raman shift (cm⁻¹)" yTitle="Week" zTitle="Intensity" aspect={{ x: 2.2, y: 1.1, z: 0.7 }} />}
          note="Left: the Raman index tracks the simulated reference glucose. Right: the responders' mean spectrum per visit; the glucose ridges at 1060 and 1125 cm⁻¹ shrink from week 0 to week 12, while the urea band at 1003 cm⁻¹ stays put." />
      </div>
    </>
  )
}

// ------------------------------------------------------------------------------------------- 6. test a sample
function TestSample({ s, dataset }: { s: UrineStudy; dataset: UrineDatasetId }) {
  const [examples, setExamples] = useState<UrineExample[]>([])
  const [res, setRes] = useState<UrineResult | null>(null)
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState('')
  const input = useRef<HTMLInputElement>(null)
  useEffect(() => { getUrineExamples().then(setExamples).catch(() => setExamples([])) }, [])
  const run = async (src: { file: File } | { example: string }, label: string) => {
    setBusy(label); setErr('')
    try { setRes(await analyzeUrine(dataset, src)) } catch (e) { setErr((e as Error).message); setRes(null) }
    setBusy('')
  }
  const groups = s.groups
  return (
    <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
      <div className="space-y-4">
        <button type="button" onClick={() => input.current?.click()} disabled={!!busy}
          className="flex w-full flex-col items-center rounded-2xl border-2 border-dashed border-accent-200 bg-accent-50/50 px-5 py-8 text-center transition hover:border-accent-400 hover:bg-accent-50">
          <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-accent-600 text-white shadow-sm">
            <svg aria-hidden viewBox="0 0 24 24" className="h-5 w-5"><path d="M12 16V4m0 0-4.5 4.5M12 4l4.5 4.5M4 16v2.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
          </span>
          <span className="mt-3 font-semibold text-slate-900">{busy === 'file' ? 'Analysing…' : 'Upload a urine spectrum'}</span>
          <span className="mt-1 text-xs text-slate-500">CSV/TXT/JSON, Raman shift covering 620–1700 cm⁻¹</span>
        </button>
        <input ref={input} type="file" className="sr-only" aria-label="Urine spectrum file" accept=".csv,.tsv,.txt,.dat,.json,.jdx,.dx"
          onChange={e => { const f = e.target.files?.[0]; e.target.value = ''; if (f) run({ file: f }, 'file') }} />
        <div className="rounded-xl border border-slate-200 bg-white">
          <p className="border-b border-slate-100 px-4 py-2.5 text-xs font-semibold tracking-wide text-slate-500 uppercase">Example urine spectra (simulated)</p>
          <ul className="divide-y divide-slate-100">
            {examples.map(e => (
              <li key={e.sample_id} className="flex items-center gap-2 px-4 py-2.5 text-sm">
                <span className="min-w-0 flex-1"><span className="block font-medium text-slate-800">{e.description}</span>
                  <span className="text-xs text-slate-500">glucose {e.concentrations_mg_dl.glucose} mg/dL · ketones {e.concentrations_mg_dl.ketones} mg/dL</span></span>
                <a href={urineExampleUrl(e.sample_id)} download className="text-slate-400 hover:text-accent-600" aria-label={`Download ${e.sample_id}`}>↓</a>
                <button className="font-medium text-accent-700 hover:underline disabled:opacity-50" disabled={!!busy} onClick={() => run({ example: e.sample_id }, e.sample_id)}>{busy === e.sample_id ? '…' : 'Analyse'}</button>
              </li>
            ))}
          </ul>
        </div>
      </div>
      <div className="min-w-0">
        {err && <p role="alert" className="mb-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-900">{err}</p>}
        {!res ? (
          <div className="flex h-full min-h-60 items-center justify-center rounded-2xl border border-slate-200 bg-mint p-8 text-center text-sm text-slate-500">
            Choose an example or upload a spectrum. It will be processed exactly like the cohort and placed among the {s.n_spectra} study spectra.
          </div>
        ) : (
          <div className="fade-up space-y-5" aria-label="Urine sample result">
            <div className="rounded-2xl border border-accent-200 bg-accent-50 p-5">
              <p className="kicker">Result · {res.sample_name}</p>
              <p className="mt-1 text-xl font-semibold text-slate-900" style={{ fontFamily: 'var(--font-serif)' }}>Closest cohort: {res.nearest_group_label}</p>
              <ul className="mt-3 space-y-1.5 text-sm text-slate-700">{res.flags.map(f => <li key={f} className="flex gap-2"><span aria-hidden className="mt-2 h-1.5 w-1.5 flex-none rounded-full bg-accent-600" />{f}</li>)}</ul>
            </div>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              {INDEX_KEYS.map(k => <Stat key={k} label={s.indices[k].label} value={fmt(res.indices[k], 3)}
                note={groups.map(g => res.index_position[k][g.id] == null ? null : (res.index_position[k][g.id] === 1 ? `Higher than every ${g.label.toLowerCase()} sample` : `Higher than ${pct(res.index_position[k][g.id]!)} of ${g.label.toLowerCase()}`)).filter(Boolean)[0] ?? undefined} />)}
              <Stat label={`Similarity to ${res.positive_label}`} value={res.similarity_to_positive.toFixed(2)} note="Model score, not a probability of disease" />
            </div>
            <FigurePair
              two={<Figure data={[...s.mean_spectra.map(m => ({ x: s.grid, y: m.mean, type: 'scatter', mode: 'lines', name: `${m.label} mean`, line: { color: color(m.group), width: 1.6 }, opacity: 0.8, hovertemplate: `${m.label}<br>%{x:.0f} cm⁻¹ · %{y:.4f}<extra></extra>` } as Data)),
                { x: res.grid, y: res.processed, type: 'scatter', mode: 'lines', name: 'Your sample', line: { color: '#0f172a', width: 2.2 }, hovertemplate: 'Your sample<br>%{x:.0f} cm⁻¹ · %{y:.4f}<extra></extra>' } as Data]}
                height={340} label="Uploaded sample over the cohort mean spectra" xTitle="Raman shift (cm⁻¹)" yTitle="Normalised intensity" layout={{ shapes: bandShapes(), annotations: bandNotes, legend: { orientation: 'h', y: 1.18, x: 0 }, margin: { t: 44, r: 16, l: 64, b: 52 } }} />}
              three={<Figure3D height={360} label="The uploaded sample placed in the cohort's 3D PCA space" xTitle="PC1" yTitle="PC2" zTitle="PC3" aspect={{ x: 1.3, y: 1.2, z: 1 }}
                data={[...groups.map(g => { const pts = s.samples.filter(p => p.group === g.id); return { type: 'scatter3d', mode: 'markers', name: g.label, x: pts.map(p => p.pc[0]), y: pts.map(p => p.pc[1]), z: pts.map(p => p.pc[2]), marker: { color: color(g.id), size: 3, opacity: 0.45 }, hoverinfo: 'skip' } as Data }),
                  { type: 'scatter3d', mode: 'markers', name: 'Your sample', x: [res.pc[0]], y: [res.pc[1]], z: [res.pc[2]], marker: { color: '#0f172a', size: 9, symbol: 'diamond', line: { color: '#fff', width: 1 } }, hovertemplate: 'Your sample<extra></extra>' } as Data]} />} />
            {res.warnings.length > 0 && <p className="text-xs text-slate-500">File notes: {res.warnings.join(' ')}</p>}
          </div>
        )}
      </div>
    </div>
  )
}

// ------------------------------------------------------------------------------------------- personal profile
const PERSON = '#0f172a' // the one highlighted individual, drawn in ink against the categorical cohorts

function PersonalProfile({ s, t }: { s: UrineStudy; t: TrialData }) {
  const people = t.participants
  const [pid, setPid] = useState(() => people.find(p => p.response === 'responder')?.participant ?? people[0].participant)
  const [loaded, setLoaded] = useState<{ pid: string; p?: UrineParticipant; error?: string } | null>(null)
  useEffect(() => {
    let live = true
    getParticipant(pid).then(p => { if (live) setLoaded({ pid, p }) }).catch(e => { if (live) setLoaded({ pid, error: (e as Error).message }) })
    return () => { live = false }
  }, [pid])
  const cur = loaded?.pid === pid ? loaded : null
  const p = cur?.p
  const groups: [string, string][] = [['control', 'Controls'], ['responder', 'Diabetes · responders'], ['non-responder', 'Diabetes · non-responders']]
  const cohortOf = (x: { arm: string; response: string }) => (x.arm === 'control' ? 'control' : x.response)

  const select = (
    <label className="block text-sm">
      <span className="text-xs font-semibold tracking-wide text-slate-500 uppercase">Participant</span>
      <select className="field mt-1.5" value={pid} onChange={e => setPid(e.target.value)} aria-label="Participant">
        {groups.map(([c, label]) => (
          <optgroup key={c} label={label}>
            {people.filter(x => cohortOf(x) === c).map(x => <option key={x.participant} value={x.participant}>{x.participant}</option>)}
          </optgroup>
        ))}
      </select>
    </label>
  )
  if (!p) return <div className="grid gap-6 lg:grid-cols-[300px_1fr]">{select}<p className="py-16 text-center text-sm text-slate-400">{cur?.error ?? 'Loading profile…'}</p></div>

  const g = p.indices.glucose
  const cohort = cohortOf(p)
  const mean = t.cohort_means.find(m => m.cohort === cohort)
  const range = g.reference_range
  const shapes: Partial<Shape>[] = [
    ...(range ? [{ type: 'rect', xref: 'paper', x0: 0, x1: 1, y0: 0, y1: range[1], fillcolor: 'rgba(42,120,214,0.10)', line: { width: 0 }, layer: 'below' } as Partial<Shape>] : []),
    ...(g.baseline != null ? [{ type: 'rect', xref: 'paper', x0: 0, x1: 1, y0: Math.max(0, g.baseline - g.rcv), y1: g.baseline + g.rcv, fillcolor: 'rgba(21,127,84,0.10)', line: { color: 'rgba(21,127,84,0.5)', width: 1, dash: 'dot' }, layer: 'below' } as Partial<Shape>] : []),
  ]
  const notes = [
    ...(range ? [{ xref: 'paper' as const, x: 0.01, y: range[1], xanchor: 'left' as const, yanchor: 'bottom' as const, text: 'Population reference range (controls, 5–95%)', showarrow: false, font: { size: 10, color: '#1c5cab' } }] : []),
    ...(g.baseline != null ? [{ xref: 'paper' as const, x: 1, y: g.baseline + g.rcv, xanchor: 'right' as const, yanchor: 'bottom' as const, text: 'Own baseline ± change limit', showarrow: false, font: { size: 10, color: '#0f6644' } }] : []),
  ]
  const trend: Data[] = [
    ...(mean ? [{ type: 'scatter', mode: 'lines', name: `${mean.label} mean`, x: t.weeks, y: mean.mean, line: { color: COHORT_COLOR[cohort], width: 1.5, dash: 'dash' }, hovertemplate: 'cohort mean %{y:.3f}<extra></extra>' } as Data] : []),
    { type: 'scatter', mode: 'lines+markers', name: `${p.participant}`, x: p.weeks, y: g.values, line: { color: PERSON, width: 2.5 },
      marker: { size: 10, color: g.in_reference_range.map(ok => (ok ? '#ffffff' : PERSON)), line: { color: PERSON, width: 2 } }, hovertemplate: `${p.participant} · week %{x}<br>glucose index %{y:.3f}<extra></extra>` } as Data,
  ]
  const ys = [...g.values.filter((v): v is number => v != null), ...(mean?.mean ?? []), g.baseline != null ? g.baseline + g.rcv : 0, range?.[1] ?? 0]
  const base3d = s.samples.filter(x => x.week === 0)
  const path3d: Data[] = [
    ...s.groups.map(gr => { const pts = base3d.filter(x => x.group === gr.id); return { type: 'scatter3d', mode: 'markers', name: gr.label, x: pts.map(x => x.pc[0]), y: pts.map(x => x.pc[1]), z: pts.map(x => x.pc[2]), marker: { color: color(gr.id), size: 3, opacity: 0.35 }, hoverinfo: 'skip' } as Data }),
    { type: 'scatter3d', mode: 'lines+markers+text', name: `${p.participant} over time`, x: p.pc_path.map(v => v[0]), y: p.pc_path.map(v => v[1]), z: p.pc_path.map(v => v[2]),
      text: p.weeks.map(w => `W${w}`), textposition: 'top center', textfont: { size: 11, color: PERSON }, line: { color: PERSON, width: 6 }, marker: { size: 5, color: PERSON },
      hovertemplate: 'week %{text}<extra></extra>' } as Data,
  ]
  const spectra3d: Data[] = [{ type: 'surface', x: p.grid, y: p.weeks, z: p.spectra, colorscale: SEQUENTIAL, showscale: false,
    contours: { y: { show: true, color: '#ffffff', width: 1 } } as never, hovertemplate: 'week %{y} · %{x:.0f} cm⁻¹ · %{z:.4f}<extra></extra>' } as Data]
  const diff: Data[] = [{ type: 'scatter', mode: 'lines', name: 'Change', x: p.grid, y: p.difference, line: { color: PERSON, width: 1.6 }, hovertemplate: '%{x:.0f} cm⁻¹ · Δ %{y:.4f}<extra></extra>' } as Data]
  const verdict = g.change == null ? '—' : g.significant ? (g.change < 0 ? 'Meaningful fall' : 'Meaningful rise') : 'Within normal variation'

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-[300px_minmax(0,1fr)]">
        <div className="space-y-4">
          {select}
          <div className="rounded-2xl border border-slate-200 bg-white p-4 text-sm">
            <p className="flex items-center gap-2 font-semibold text-slate-900"><span aria-hidden className="h-2.5 w-2.5 rounded-full" style={{ background: COHORT_COLOR[cohort] }} />{p.participant}</p>
            <p className="mt-1 text-slate-600">{p.arm === 'control' ? 'Normoglycaemic control' : `Type 2 diabetes · ${p.response}`}</p>
            <p className="mt-1 text-xs text-slate-500">Visits at weeks {p.weeks.join(', ')}</p>
          </div>
        </div>
        <div className="rounded-2xl border border-accent-200 bg-accent-50 p-5" aria-label="Personalised read-out">
          <p className="kicker">Personalised read-out · {p.participant}</p>
          <ul className="mt-3 space-y-2 text-sm leading-relaxed text-slate-800">
            {p.insights.map(x => <li key={x} className="flex gap-2"><span aria-hidden className="mt-2 h-1.5 w-1.5 flex-none rounded-full bg-accent-600" />{x}</li>)}
          </ul>
          <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Own baseline (week 0)" value={fmt(g.baseline, 3)} note="Glucose index" />
            <Stat label={`Latest (week ${p.weeks[p.weeks.length - 1]})`} value={fmt(g.latest, 3)} note={g.change_pct != null ? `${g.change_pct > 0 ? '+' : ''}${Math.round(g.change_pct * 100)}% vs own baseline` : undefined} />
            <Stat label="Personal change limit" value={`± ${fmt(g.rcv, 2)}`} note="Reference change value at this baseline" />
            <Stat label="Verdict" value={verdict} note={range ? `Population range ≤ ${fmt(range[1], 3)}` : undefined} />
          </div>
        </div>
      </div>

      <FigurePair
        two={<Figure data={trend} height={360} label="This participant's glucose index against their own baseline band and the population reference range" xTitle="Week of follow-up" yTitle="Glucose index (/ creatinine)"
          layout={{ shapes, annotations: notes, xaxis: { tickvals: p.weeks, gridcolor: '#eef2f7' }, yaxis: { range: [0, Math.max(...ys) * 1.12], gridcolor: '#eef2f7' }, legend: { orientation: 'h', y: 1.14, x: 0 }, margin: { t: 40, r: 16, l: 64, b: 52 } }} />}
        three={<Figure3D data={path3d} height={380} label="This participant's path through the cohort's PCA space, visit by visit" xTitle="PC1" yTitle="PC2" zTitle="PC3" aspect={{ x: 1.3, y: 1.2, z: 1 }} />}
        note={<>Left: the green band is this person's own baseline ± the change that normal visit-to-visit variation can produce; the blue band is the population reference range. Hollow markers are visits inside the population range. Right: the same visits as a path through the whole-spectrum PCA space of the cohort.</>} />
      <FigurePair
        two={<Figure data={diff} height={300} label="Spectral change from this participant's first to last visit" xTitle="Raman shift (cm⁻¹)" yTitle={`Δ intensity (week ${p.weeks[p.weeks.length - 1]} − week 0)`}
          layout={{ shapes: [...bandShapes(), { type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 0, y1: 0, line: { color: '#94a3b8', width: 1 } }], annotations: bandNotes, margin: { t: 28, r: 16, l: 64, b: 52 } }} />}
        three={<Figure3D data={spectra3d} height={340} label="This participant's urine spectrum at every visit as a 3D surface" xTitle="Raman shift (cm⁻¹)" yTitle="Week" zTitle="Intensity" aspect={{ x: 2.2, y: 1.1, z: 0.7 }} />}
        note="What changed in this person's urine chemistry: the difference between the last and first visit, and the full spectrum at every visit." />

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="w-full min-w-[560px] text-sm">
          <caption className="px-4 pt-3 pb-1 text-left text-sm font-medium text-slate-800">Band indices per visit · ● outside the population reference range</caption>
          <thead><tr className="border-b border-slate-200 text-left text-xs text-slate-500"><th className="px-4 py-2 font-medium">Index</th>{p.weeks.map(w => <th key={w} className="px-4 py-2 font-medium">Week {w}</th>)}<th className="px-4 py-2 font-medium">Change vs own baseline</th></tr></thead>
          <tbody className="tabular-nums">
            {INDEX_KEYS.map(k => {
              const ix = p.indices[k]
              return (
                <tr key={k} className="border-b border-slate-100 last:border-0">
                  <th className="px-4 py-2 text-left font-medium text-slate-700">{ix.label}</th>
                  {ix.values.map((v, i) => <td key={i} className="px-4 py-2">{fmt(v, 3)}{ix.in_reference_range[i] === false && <span className="ml-1 text-slate-900" aria-label="outside reference range">●</span>}</td>)}
                  <td className="px-4 py-2">{ix.change == null ? '—' : `${ix.change > 0 ? '+' : ''}${fmt(ix.change, 3)}`} <span className={`ml-1 text-xs ${ix.significant ? 'font-semibold text-accent-800' : 'text-slate-400'}`}>{ix.change == null ? '' : ix.significant ? 'meaningful' : 'within noise'}</span></td>
                </tr>
              )
            })}
          </tbody>
        </table>
        <p className="border-t border-slate-100 px-4 py-2.5 text-xs leading-relaxed text-slate-500">
          Change limit (reference change value) = 1.96·√2·√(SD<sub>w</sub>² + (CV·baseline)²). SD<sub>w</sub> = {fmt(p.reference_change.glucose.sd_within, 4)} is measured from the visit-to-visit spread of {p.reference_change.glucose.n_people} control participants;
          the within-person CV of {Math.round(p.reference_change.glucose.cv_assumed * 100)}% for glucose and ketones is an assumption until repeat samples from stable patients are available.
        </p>
      </div>
    </div>
  )
}

// ------------------------------------------------------------------------------------------- roadmap
function Roadmap() {
  return (
    <ol className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      {PROGRAMME.map((ph, k) => (
        <li key={ph.phase} className={`relative flex flex-col rounded-2xl border bg-white p-5 ${k === 0 ? 'border-accent-300 ring-2 ring-accent-100' : 'border-slate-200'}`}>
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-semibold text-accent-700 tabular-nums">{ph.phase}</span>
            <span className={`badge ${STATUS_STYLE[ph.status]}`}>{ph.status}</span>
          </div>
          <p className="mt-2 text-lg font-semibold text-slate-900" style={{ fontFamily: 'var(--font-serif)' }}>{ph.title}</p>
          <p className="mt-1.5 text-sm leading-relaxed text-slate-600">{ph.body}</p>
          <ul className="mt-3 space-y-1 border-t border-slate-100 pt-3 text-xs text-slate-500">
            {ph.items.map(it => <li key={it} className="flex gap-2"><span aria-hidden className="mt-1.5 h-1 w-1 flex-none rounded-full bg-accent-500" />{it}</li>)}
          </ul>
        </li>
      ))}
    </ol>
  )
}

// ------------------------------------------------------------------------------------------- page
const NAV = [['cohort', 'Cohort spectra'], ['biomarkers', 'Biomarker bands'], ['pca', 'PCA'], ['classification', 'Screening'], ['trial', 'Trial follow-up'],
  ['personal', 'Personal profile'], ['test', 'Test a sample'], ['roadmap', 'Roadmap']] as const

export function Diabetes({ onAnalyze }: { onAnalyze?: () => void }) {
  const [dataset, setDataset] = useState<UrineDatasetId>('trial')
  // Results are tagged with their dataset, so a pending switch shows "loading" instead of the previous dataset.
  const [loaded, setLoaded] = useState<{ dataset: UrineDatasetId; study?: UrineStudy; error?: string } | null>(null)
  useEffect(() => {
    let live = true
    getUrineStudy(dataset).then(study => { if (live) setLoaded({ dataset, study }) })
      .catch(e => { if (live) setLoaded({ dataset, error: (e as Error).message }) })
    return () => { live = false }
  }, [dataset])
  const current = loaded?.dataset === dataset ? loaded : null
  const s = current?.study ?? null
  const error = current?.error ?? ''
  const nav = useMemo(() => NAV.filter(([id]) => (id !== 'trial' && id !== 'personal') || s?.trial), [s])
  const num = (id: string) => String(nav.findIndex(([i]) => i === id) + 1).padStart(2, '0')
  const measured = s?.dataset.category === 'measured'

  return (
    <div>
      <header className="bg-grid relative overflow-hidden border-b border-accent-100 bg-mint">
        <div className="mx-auto grid max-w-7xl gap-10 px-4 py-14 sm:px-6 lg:grid-cols-[1.4fr_1fr] lg:py-16">
          <div>
            <p className="kicker">Personalised healthcare programme · Study 1</p>
            <h1 className="mt-3 text-4xl font-semibold tracking-tight text-balance text-slate-900 sm:text-5xl" style={{ fontFamily: 'var(--font-serif)' }}>
              Diabetes: reading each person's metabolic state from the Raman fingerprint of urine
            </h1>
            <p className="mt-5 max-w-2xl text-lg leading-relaxed text-pretty text-slate-600">
              Diabetes is where the programme starts. Glucose, ketones, urea and creatinine each leave characteristic bands in a urine Raman spectrum.
              We use them to understand cohorts and, above all, each individual: their own baseline, how they respond to therapy, and when a change is real rather than noise.
            </p>
            <ol aria-label="Programme" className="mt-6 flex flex-wrap items-center gap-2 text-xs">
              {PROGRAMME.map((ph, k) => (
                <li key={ph.phase}>
                  <a href="#roadmap" className={`inline-block rounded-full px-3 py-1 font-medium transition ${k === 0 ? 'bg-accent-600 text-white' : 'border border-accent-200 bg-white text-slate-600 hover:border-accent-400'}`}>{ph.title}</a>
                </li>
              ))}
            </ol>
          </div>
          <div className="self-end">
            <p className="mb-2 text-xs font-semibold tracking-wide text-slate-500 uppercase">Dataset</p>
            <div role="radiogroup" aria-label="Dataset" className="grid gap-2">
              {DATASETS.map(d => (
                <button key={d.id} role="radio" aria-checked={dataset === d.id} onClick={() => setDataset(d.id)}
                  className={`flex items-center justify-between gap-3 rounded-xl border px-4 py-3 text-left transition ${dataset === d.id ? 'border-accent-600 bg-white shadow-sm ring-2 ring-accent-100' : 'border-slate-200 bg-white/70 hover:border-accent-300'}`}>
                  <span><span className="block font-semibold text-slate-900">{d.label}</span><span className="text-xs text-slate-500">{d.sub}</span></span>
                  <span aria-hidden className={`h-4 w-4 flex-none rounded-full border-2 ${dataset === d.id ? 'border-accent-600 bg-accent-600 shadow-[inset_0_0_0_2px_#fff]' : 'border-slate-300'}`} />
                </button>
              ))}
            </div>
          </div>
        </div>
      </header>

      <nav aria-label="Study sections" className="no-print sticky top-[61px] z-20 border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl gap-1 overflow-x-auto px-4 py-2 text-sm sm:px-6">
          {nav.map(([id, label]) => <a key={id} href={`#${id}`} className="rounded-lg px-3 py-1.5 whitespace-nowrap text-slate-600 transition hover:bg-accent-50 hover:text-accent-800">{label}</a>)}
        </div>
      </nav>

      <div className="mx-auto max-w-7xl px-4 sm:px-6">
        {error && <p role="alert" className="mt-8 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-900">{error.includes('reach') || error.includes('fetch') ? 'The analysis server is not reachable. Start the backend and reload this page.' : error}</p>}
        {!s && !error && <p className="py-24 text-center text-sm text-slate-400">Loading study data…</p>}
        {s && (
          <>
            <div className="mt-8 grid gap-4 rounded-2xl border border-slate-200 bg-white p-5 lg:grid-cols-[1fr_auto]">
              <div className="text-sm leading-relaxed text-slate-600">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`badge ${measured ? 'bg-sky-50 text-sky-800 ring-1 ring-sky-200' : 'bg-amber-50 text-amber-800 ring-1 ring-amber-200'}`}>{measured ? 'Measured data' : 'Simulated data'}</span>
                  <span className="font-semibold text-slate-900">{s.dataset.name}</span>
                </div>
                <p className="mt-2">{measured ? s.dataset.citation : s.dataset.design}</p>
                {s.dataset.caveat && <p className="mt-1 text-slate-500">{s.dataset.caveat}</p>}
                <p className="mt-1 text-xs text-slate-500">{s.dataset.instrument ?? `${s.dataset.excitation_nm} nm excitation`} · {s.processing} · Licence: {s.dataset.license}{s.dataset.url && <> · <a className="font-medium text-accent-700 hover:underline" href={s.dataset.url} target="_blank" rel="noreferrer">Source</a></>}</p>
              </div>
              <dl className={`grid self-start gap-3 text-center lg:min-w-96 ${s.groups.length > 2 ? 'grid-cols-3' : 'grid-cols-2'}`}>
                {s.groups.map(g => (
                  <div key={g.id} className="rounded-xl bg-slate-50 px-3 py-2">
                    <dt className="flex items-center justify-center gap-1.5 text-[11px] text-slate-500"><span aria-hidden className="h-2 w-2 rounded-full" style={{ background: color(g.id) }} />{g.label}</dt>
                    <dd className="text-xl font-semibold text-slate-900 tabular-nums">{g.n}<span className="ml-1 text-[11px] font-normal text-slate-400">spectra</span></dd>
                  </div>
                ))}
              </dl>
            </div>

            <Section id="cohort" n={`${num('cohort')} · Spectra`} title="What diabetic urine looks like to a Raman spectrometer"
              lede={<>Mean spectra per cohort after baseline removal and normalisation. Glycosuria adds intensity at the glucose bands (1060 and 1125 cm⁻¹), next to the dominant urea band at 1003 cm⁻¹.</>}>
              <CohortSpectra s={s} />
            </Section>
            <Section id="biomarkers" n={`${num('biomarkers')} · Biomarkers`} title="Band indices: reading chemistry from peak heights"
              lede="Each solute's strongest bands give a dilution-corrected index. The glucose index is the main screening and monitoring marker; ketones flag possible ketoacidosis; urea gives context.">
              <Biomarkers s={s} />
            </Section>
            <Section id="pca" n={`${num('pca')} · Multivariate`} title="Principal component analysis of the whole spectrum"
              lede="PCA summarises all 700 wavenumbers in a few components. Points are individual urine samples (baseline visit for the trial).">
              <Pca s={s} />
            </Section>
            <Section id="classification" n={`${num('classification')} · Screening model`} title={`Can the spectrum flag ${s.groups.find(g => g.id === s.positive_group)?.label}?`}
              lede="A cross-validated classifier on the PCA scores. Every number below comes from samples the model did not see during training.">
              <Classification s={s} />
            </Section>
            {s.trial && (
              <Section id="trial" n={`${num('trial')} · Follow-up`} title="Monitoring response to therapy over 12 weeks"
                lede="Each participant gave a urine sample at weeks 0, 4, 8 and 12. Falling glucose bands show glycaemic control improving, without a blood draw.">
                <Trial t={s.trial} grid={s.grid} />
              </Section>
            )}
            {s.trial && (
              <Section id="personal" n={`${num('personal')} · Personalised`} title="From population averages to the individual"
                lede={<>Population cut-offs say whether someone looks like a cohort. Personalised monitoring asks a different question: <b className="font-medium text-slate-800">has this person changed, relative to themselves?</b> Each participant's visits are compared with their own week-0 baseline, using a change limit derived from normal visit-to-visit variation.</>}>
                <PersonalProfile s={s} t={s.trial} />
              </Section>
            )}
            <Section id="test" n={`${num('test')} · Try it`} title="Place your own urine spectrum in the study"
              lede={<>Upload a urine Raman spectrum (ideally 785 nm). It is processed like the cohort, its band indices are compared with each group, and it is projected into the PCA space. For a general material identification use <button className="font-medium text-accent-700 hover:underline" onClick={onAnalyze}>Analyze</button>.</>}>
              <TestSample key={dataset} s={s} dataset={dataset} />
            </Section>
            <Section id="roadmap" n={`${num('roadmap')} · Roadmap`} title="From diabetes to personalised healthcare"
              lede="This study is the first step. The same pipeline (spectral processing, band indices, population models and personal baselines) is designed to extend to further conditions, other biofluids, and long-term health records for each individual.">
              <Roadmap />
            </Section>
          </>
        )}
      </div>
    </div>
  )
}
