"""Self-contained HTML research brief. Print-friendly, so the browser's "Save as PDF" gives a two-page PDF."""
import math
from datetime import datetime
from html import escape

ACCENT, PEAK, BASE = "#1f45b8", "#e11d48", "#d97706"


def _ticks(lo, hi, n=5):
    if hi <= lo:
        return [lo]
    raw = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    t, out = math.ceil(lo / step) * step, []
    while t <= hi + 1e-9 * abs(hi - lo):
        out.append(t)
        t += step
    return out


def chart(series, xlabel, ylabel, w=760, h=260, points=()):
    """series: [(name, xs, ys, colour, dashed)]; points: [(x, y, label)]. Plain SVG with labelled axes."""
    xs_all = [v for s in series for v in s[1] if v is not None]
    ys_all = [v for s in series for v in s[2] if v is not None] + [p[1] for p in points]
    if not xs_all or not ys_all:
        return ""
    x0, x1, y0, y1 = min(xs_all), max(xs_all), min(ys_all), max(ys_all)
    if x1 == x0:
        x0, x1 = x0 - 1, x1 + 1
    pad = (y1 - y0) * 0.08 or 1.0
    y0, y1 = y0 - pad, y1 + pad * (2.4 if points else 1)
    L, R, T, B = 60, 12, 10, 42
    X = lambda v: L + (v - x0) / (x1 - x0) * (w - L - R)
    Y = lambda v: h - B - (v - y0) / (y1 - y0) * (h - T - B)
    g = [f'<line x1="{L}" x2="{w - R}" y1="{h - B}" y2="{h - B}" stroke="#94a3b8"/>']
    for t in _ticks(x0, x1, 6):
        g.append(f'<line x1="{X(t):.1f}" x2="{X(t):.1f}" y1="{T}" y2="{h - B}" stroke="#f1f5f9"/>'
                 f'<text x="{X(t):.1f}" y="{h - B + 14}" class="tk" text-anchor="middle">{t:g}</text>')
    for t in _ticks(y0, y1, 4):
        g.append(f'<text x="{L - 6}" y="{Y(t) + 3:.1f}" class="tk" text-anchor="end">{t:.2g}</text>')
    for _, xs, ys, colour, dashed in series:
        pts = [(X(a), Y(b)) for a, b in zip(xs, ys) if a is not None and b is not None]
        step = max(1, len(pts) // 900)
        dash = ' stroke-dasharray="5 4"' if dashed else ""
        g.append(f'<polyline fill="none" stroke="{colour}" stroke-width="1.5"{dash} '
                 'stroke-linejoin="round" points="' + " ".join(f"{a:.1f},{b:.1f}" for a, b in pts[::step]) + '"/>')
    for px, py, lab in points:
        g.append(f'<circle cx="{X(px):.1f}" cy="{Y(py):.1f}" r="2.6" fill="{PEAK}"/>'
                 f'<text x="{X(px):.1f}" y="{Y(py) - 6:.1f}" class="pk" text-anchor="middle">{escape(str(lab))}</text>')
    g.append(f'<text x="{(L + w - R) / 2}" y="{h - 6}" class="ax" text-anchor="middle">{escape(xlabel)}</text>'
             f'<text transform="translate(13 {(T + h - B) / 2}) rotate(-90)" class="ax" text-anchor="middle">{escape(ylabel)}</text>')
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="{escape(ylabel)} against {escape(xlabel)}">'
            + "".join(g) + "</svg>")


def _table(head, rows):
    return ("<table><thead><tr>" + "".join(f"<th>{escape(h)}</th>" for h in head) + "</tr></thead><tbody>"
            + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows) + "</tbody></table>")


def _ul(items):
    items = list(items)
    return "<ul>" + "".join(f"<li>{escape(str(i))}</li>" for i in items) + "</ul>" if items else ""


CSS = """*{box-sizing:border-box}body{font:13.5px/1.55 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;color:#0f172a;
background:#fff;max-width:820px;margin:0 auto;padding:36px 28px}
.top{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:2px solid #0f172a;padding-bottom:10px}
.brand{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:#64748b;font-weight:600}
h1{font-size:22px;letter-spacing:-.01em;margin:2px 0 0}.meta{font-size:11.5px;color:#64748b;text-align:right;line-height:1.5}
h2{font-size:11.5px;letter-spacing:.12em;text-transform:uppercase;color:#1f45b8;margin:22px 0 8px}
.verdict{margin:18px 0 0;padding:14px 16px;border-left:4px solid #1f45b8;background:#f5f7ff}
.verdict.inc{border-color:#d97706;background:#fffbeb}.verdict b{display:block;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:#64748b}
.verdict p{margin:2px 0 0;font-size:15.5px;font-weight:600}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:14px}.kpi{border:1px solid #e2e8f0;border-radius:8px;padding:8px 10px}
.kpi span{display:block;font-size:10.5px;color:#64748b}.kpi strong{font-size:17px}.kpi small{display:block;font-size:9.5px;color:#94a3b8}
table{border-collapse:collapse;width:100%;font-size:12.5px}th{text-align:left;font-weight:600;color:#475569;border-bottom:1px solid #cbd5e1;padding:5px 6px}
td{border-bottom:1px solid #eef2f7;padding:5px 6px;vertical-align:top}td.n{font-variant-numeric:tabular-nums}
.cap{font-size:11px;color:#64748b;margin:4px 0 0}.two{display:grid;grid-template-columns:1fr 1fr;gap:22px}
ul{margin:0;padding-left:17px}li{margin:2px 0}.tk{font-size:9.5px;fill:#64748b}.ax{font-size:10.5px;fill:#334155}.pk{font-size:9px;fill:#be123c;font-weight:600}
.foot{margin-top:24px;border-top:1px solid #e2e8f0;padding-top:8px;font-size:10.5px;color:#64748b}
@media (max-width:640px){.kpis,.two{grid-template-columns:1fr 1fr}.two{grid-template-columns:1fr}}
@media print{body{padding:0}section,table,svg{break-inside:avoid}@page{margin:14mm}}"""


def build(r: dict) -> str:
    b = r["brief"]
    sp = r["sections"]["spectrum"]["data"]
    when = datetime.fromisoformat(r["generated_at"]).strftime("%d %b %Y, %H:%M UTC")
    inc = not b["match_claimed"]
    kpis = "".join(f'<div class="kpi"><span>{escape(m["label"])}</span><strong>{escape(m["value"])}</strong>'
                   + (f'<small>{escape(m["note"])}</small>' if m.get("note") else "") + "</div>" for m in b["metrics"])
    top = sorted(sp["peaks"], key=lambda p: -p["relative_height"])[:10]
    fig = chart([("Processed", sp["x"], sp["processed"], ACCENT, False)], "Raman shift (cm⁻¹)", "Normalised intensity (a.u.)",
                points=[(p["position"], p["height"], f'{p["position"]:.0f}') for p in top])
    peaks = _table(["Position (cm⁻¹)", "Rel. intensity", "Tentative region", "Matching reference band"], [
        [f'<span class="n">{p["position"]:.0f}</span>', f'{p["relative_height"]:.2f}', escape(p["assignment"] or "—"),
         escape(p["reference"] or "—")] for p in b["peaks"]])
    refs = _table(["Reference", "Similarity", "Coverage"], [
        [escape(m["name"]) + (" ✓" if i == 0 and not inc else ""), f'{m["score"]:.3f}', f'{100 * m["coverage"]:.0f}%']
        for i, m in enumerate(b["references"])])
    np_ = "; ".join(f'{x["title"]} ({x["reason"]})' for x in b["not_performed"])
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>Raman analysis – {escape(r["sample_id"])}</title><style>{CSS}</style></head><body>'
            f'<div class="top"><div><div class="brand">RamanReach · Research report</div><h1>Raman Spectral Analysis</h1></div>'
            f'<div class="meta">Sample <b>{escape(r["sample_id"])}</b><br>Report {escape(b["report_id"])}<br>{escape(when)}</div></div>'
            f'<div class="verdict{" inc" if inc else ""}"><b>{escape(b["verdict"])}</b><p>{escape(b["headline"])}</p></div>'
            f'<div class="kpis">{kpis}</div>'
            f'<section><h2>Summary of findings</h2>{_ul(b["findings"])}</section>'
            f'<section><h2>Figure 1 · Processed spectrum</h2>{fig}<p class="cap">Baseline-corrected and normalised; '
            f'labels mark the ten most intense peaks (cm⁻¹).</p></section>'
            f'<section><h2>Table 1 · Principal peaks</h2>{peaks}<p class="cap">Regions are tentative textbook ranges, not '
            f'assignments.</p></section>'
            f'<section class="two"><div><h2>Table 2 · Reference comparison</h2>{refs}<p class="cap">Cosine similarity of band '
            f'shape; not a probability of identity.</p></div><div><h2>Reliability</h2>{_ul(b["limitations"])}</div></section>'
            f'<section><h2>Conclusion and recommendations</h2><p>{escape(b["headline"])} '
            + ("The evidence does not meet the criteria for a match claim." if inc else
               "This is a provisional similarity result, not a validated identification.")
            + f'</p>{_ul(b["recommendations"])}</section>'
            f'<div class="foot"><b>Methods.</b> {escape(b["methods"])}'
            + (f' <b>Not performed:</b> {escape(np_)}.' if np_ else "")
            + f' RamanReach {escape(str(r["software_version"]))}. Research use only; not for diagnostic or safety decisions.</div>'
            '</body></html>')
