"""Self-contained HTML report laid out as a laboratory report: letterhead, sample information, result summary, figures
and quality control on page 1, a technical appendix on page 2. Print-friendly; the browser's "Save as PDF" gives the PDF."""
import math
from datetime import datetime
from html import escape

PEAK = "#52514e"


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
        step = max(1, len(pts) // 500)  # ~1 point per 1.5 px of plot width
        dash = ' stroke-dasharray="5 4"' if dashed else ""
        g.append(f'<polyline fill="none" stroke="{colour}" stroke-width="2"{dash} '
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


SAMPLE, REFERENCE = "#2a78d6", "#eb6834"  # validated pair (dataviz validator)
GREEN, GREEN_DARK, GREEN_TINT, INK, MUTED = "#157f54", "#0b432e", "#f0faf4", "#0f172a", "#64748b"
GOOD, CRITICAL = "#0ca30c", "#d03b3b"

CSS = """*{box-sizing:border-box;-webkit-print-color-adjust:exact;print-color-adjust:exact}
body{font:12.5px/1.55 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;color:#0f172a;background:#fff;max-width:860px;margin:0 auto;padding:0 28px 32px}
.serif,h1,h2{font-family:"Source Serif 4",Georgia,"Times New Roman",serif}
.band{height:6px;background:linear-gradient(90deg,#0b432e,#157f54 60%,#4fb985)}
.head{display:flex;justify-content:space-between;align-items:flex-start;gap:24px;padding:18px 0 14px;border-bottom:1.5px solid #0b432e}
.brand{display:flex;gap:10px;align-items:center}.brand b{display:block;font-size:15px}.brand span{font-size:10.5px;color:#64748b;letter-spacing:.04em}
.idt{font-size:10.5px;border-collapse:collapse;width:auto}.idt td{padding:1px 0 1px 12px;border:0}.idt td:first-child{color:#64748b;text-align:right}
h1{font-size:23px;font-weight:600;margin:18px 0 2px;letter-spacing:-.01em}.sub{color:#64748b;font-size:11.5px;margin:0 0 14px}
h2{font-size:15px;font-weight:600;color:#0b432e;margin:22px 0 8px;padding-bottom:4px;border-bottom:1px solid #dcf3e5}
h2 .n{color:#157f54;margin-right:6px}h3{font-size:12px;margin:14px 0 6px;color:#334155;text-transform:uppercase;letter-spacing:.06em}
.result{border:1px solid #b9e6cb;border-left:5px solid var(--c);background:#f5fbf7;border-radius:8px;padding:14px 16px}
.result .k{font-size:10px;letter-spacing:.12em;text-transform:uppercase;font-weight:700;color:var(--c)}
.result .hl{font-size:18px;font-weight:600;line-height:1.3;margin:3px 0 6px}.result p{margin:0;color:#334155}
.kpis{display:grid;grid-template-columns:repeat(5,1fr);margin-top:10px;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden}
.kpi{padding:7px 10px;border-left:1px solid #e2e8f0}.kpi:first-child{border-left:0}.kpi span{display:block;font-size:9.5px;color:#64748b;text-transform:uppercase;letter-spacing:.05em}
.kpi strong{font-size:15px}.kpi small{display:block;font-size:9px;color:#94a3b8}
table{border-collapse:collapse;width:100%;font-size:11px}th{text-align:left;font-weight:600;color:#0b432e;background:#f0faf4;border-bottom:1px solid #b9e6cb;padding:5px 7px}
td{border-bottom:1px solid #eef2f7;padding:4px 7px;vertical-align:top}.info td:first-child{color:#64748b;width:32%}
.fig{border:1px solid #e2e8f0;border-radius:8px;padding:10px 10px 6px;margin-top:4px}
.cap{font-size:10.5px;color:#475569;margin:6px 0 0}.cap b{color:#0f172a}
.legend{font-size:11px;color:#334155;margin:0 0 4px}.legend i{display:inline-block;width:14px;height:3px;border-radius:2px;vertical-align:middle;margin:0 5px 0 12px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:24px}
.pill{display:inline-block;font-size:9.5px;font-weight:700;letter-spacing:.06em;border-radius:999px;padding:1px 8px;color:#fff}
.bar{height:6px;border-radius:4px;background:#eef2f7;flex:1;min-width:110px}.bar i{display:block;height:100%;border-radius:4px}
.rb{display:flex;align-items:center;gap:8px}.rb span{font-size:10.5px;width:28px;text-align:right;font-weight:600}
.rank td{vertical-align:middle;padding:6px 7px}.rank td:nth-child(3),.rank td:nth-child(4),.rank th:nth-child(3),.rank th:nth-child(4){text-align:right}
.rk{display:inline-flex;width:20px;height:20px;border-radius:50%;align-items:center;justify-content:center;background:#f1f5f9;color:#475569;font-size:10px;font-weight:700}.rk.top{background:#0f6644;color:#fff}
ul{margin:0;padding-left:16px}li{margin:3px 0}.facts{font-size:10.5px;color:#475569}
.tk{font-size:9.5px;fill:#64748b}.ax{font-size:10.5px;fill:#334155}.pk{font-size:9.5px;fill:#52514e}
.appendix{break-before:page;margin-top:30px}
.sign{display:grid;grid-template-columns:1fr 1fr 1fr;gap:20px;margin-top:22px;font-size:10.5px;color:#64748b}
.sign div{border-top:1px solid #94a3b8;padding-top:4px}
.foot{margin-top:18px;border-top:1px solid #e2e8f0;padding-top:8px;font-size:9.5px;color:#64748b;display:flex;justify-content:space-between;gap:16px}
@media (max-width:640px){.two,.kpis,.sign{grid-template-columns:1fr}.head{flex-direction:column}}
@media print{body{padding:0}section,table,svg,.result,.fig{break-inside:avoid}@page{margin:13mm 14mm}}"""

LOGO = ('<svg width="34" height="34" viewBox="0 0 36 36" aria-hidden="true"><rect width="36" height="36" rx="10" fill="#157f54"/>'
        '<path d="M6 25 L11 24 L13 12 L15 24 L19 21 L21.5 8 L24 23 L30 24" fill="none" stroke="#fff" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round"/></svg>')
STATUS = {3: ("Confirmed match", GREEN), 2: ("Probable match", GREEN), 1: ("Closest reference match", "#0f766e"),
          0: ("No confident match", "#475569")}


def _h2(n, title):
    return f'<h2><span class="n">{n}</span>{escape(title)}</h2>'


def _library(r):
    p = r["data_provenance"]
    cats = p.get("references_by_category") or {}
    names = {"measured": "measured (RRUFF/ROD)", "synthetic": "synthetic literature-band"}
    parts = ", ".join(f"{n} {names.get(c, c)}" for c, n in cats.items())
    return f'{p.get("n_materials", "—")} materials, {p.get("n_reference_spectra", "—")} spectra' + (f" ({parts})" if parts else "")


def build(r: dict) -> str:
    b = r["brief"]
    v = r.get("visual") or {}
    e = r.get("explanation") or {}
    sp = r["sections"]["spectrum"]["data"]
    val = r["sections"]["validation"]["data"]
    when = datetime.fromisoformat(r["generated_at"]).strftime("%d %b %Y, %H:%M UTC")
    found = [f["text"] for f in e.get("what_we_found", [])][:4] or b["findings"]
    nxt = (e.get("next_steps") or b["recommendations"])[:4]
    top = sorted(sp["peaks"], key=lambda p: -p["relative_height"])[:10]
    params = sp.get("parameters") or {}
    rng = val.get("range_cm1") or [None, None]
    exc = (r.get("analysis") or {}).get("excitation_nm") or r["inputs"]["metadata"].get("excitation_nm")
    info = _table(["Item", "Value"], [
        ["Sample ID", f'<b>{escape(r["sample_id"])}</b>'],
        ["Source", escape(str(r.get("source", "—")))],
        ["Spectral data", f'{val.get("points", "—")} points, {rng[0]:.0f}–{rng[1]:.0f} cm⁻¹' if rng[0] is not None else "—"],
        ["Excitation wavelength", f"{exc:g} nm" if exc else "Not stated in file"],
        ["Spectra in file", str(r["inputs"].get("n_spectra", 1))],
        ["Reference library", escape(_library(r))],
        ["Processing", escape(f'Despike, {params.get("baseline", "als").upper()} baseline, '
                              f'{params.get("smoothing", "savgol")} smoothing, {params.get("normalization", "vector")} normalisation')],
    ]).replace("<table>", '<table class="info">', 1)
    tech_fig = chart([("Processed", sp["x"], sp["processed"], SAMPLE, False)], "Raman shift (cm⁻¹)", "Processed intensity (a.u.)",
                     h=220, points=[(p["position"], p["height"], f'{p["position"]:.0f}') for p in top])
    peaks = _table(["#", "Position (cm⁻¹)", "Rel. intensity", "Tentative region"], [
        [str(i + 1), f'{p["position"]:.0f}', f'{p["relative_height"]:.2f}', escape(p["assignment"] or "—")] for i, p in enumerate(b["peaks"])])
    lims = b["limitations"] + ([r["evaluation"]["headline"]] if (r.get("evaluation") or {}).get("headline") else [])
    facts = "".join(f'<li><b>{escape(x["id"])}</b> {escape(x["label"])}: {escape(x["text"])}</li>' for x in e.get("evidence", []))
    np_ = "; ".join(f'{x["title"]} ({x["reason"]})' for x in b["not_performed"])
    sig = lambda title: f'<div>{escape(title)}</div>'
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
        'family=Inter:wght@400;600;700&family=Source+Serif+4:opsz,wght@8..60,600&display=swap">'
        f'<title>Raman analysis report – {escape(r["sample_id"])}</title><style>{CSS}</style></head><body><div class="band"></div>'
        f'<header class="head"><div class="brand">{LOGO}<div><b>RamanReach</b><span>SPECTROSCOPY RESEARCH LAB</span></div></div>'
        + _table_plain([["Report ID", escape(b["report_id"])], ["Issued", escape(when)], ["Software", f'RamanReach {escape(str(r["software_version"]))}'],
                        ["Classification", "Research use"]])
        + '</header>'
        f'<h1>Raman Spectrum Analysis Report</h1><p class="sub">Automated processing, peak detection and reference comparison</p>'
        + _h2("1", "Sample information") + info
        + _h2("2", "Result summary") + _result(r, v, e)
        + _h2("3", "Spectral comparison") + _overlay(v)
        + (f'<section>{_h2("4", "Candidate ranking")}{_ranking(v)}</section>'
           f'<section>{_h2("5", "Quality control")}{_checks(v)}</section>' if v else "")
        + f'<section class="two"><div>{_h2("6", "Interpretation")}{_ul(found)}</div><div>{_h2("7", "Recommendations")}{_ul(nxt)}</div></section>'
        + f'<div class="sign">{sig("Analysed by: RamanReach automated pipeline")}{sig("Reviewed by")}{sig("Date")}</div>'
        + _foot(r, 1)
        + f'<section class="appendix">{_h2("A", "Technical appendix")}'
        f'<div class="kpis" style="grid-template-columns:repeat({len(b["metrics"])},1fr)">'
        + "".join(f'<div class="kpi"><span>{escape(m["label"])}</span><strong>{escape(m["value"])}</strong>'
                  + (f'<small>{escape(m["note"])}</small>' if m.get("note") else "") + "</div>" for m in b["metrics"]) + "</div>"
        f'<h3>Processed spectrum</h3><div class="fig">{tech_fig}<p class="cap"><b>Figure 2.</b> Processed spectrum with the ten strongest '
        'detected peaks labelled by position (cm⁻¹).</p></div>'
        f'<div class="two"><div><h3>Table 1 · Principal peaks</h3>{peaks}<p class="cap">Regions are tentative textbook ranges, not assignments.</p></div>'
        f'<div><h3>Method notes and limitations</h3>{_ul(lims)}</div></div>'
        + (f'<h3>Evidence behind the summary</h3><ul class="facts">{facts}</ul>' if facts else "")
        + f'<h3>Methods</h3><p class="cap">{escape(b["methods"])}' + (f' <b>Not performed:</b> {escape(np_)}.' if np_ else "") + "</p>"
        + _foot(r, 2) + '</section></body></html>')


def _table_plain(rows):
    return '<table class="idt">' + "".join(f"<tr><td>{a}</td><td><b>{b_}</b></td></tr>" for a, b_ in rows) + "</table>"


def _foot(r, page):
    return (f'<div class="foot"><span>Research use only; not for clinical, legal or safety decisions. Similarity scores rank band-shape '
            f'agreement and are not a probability of identification.</span><span>{escape(r["brief"]["report_id"])} · page {page}</span></div>')


def _result(r, v, e):
    c = v.get("confidence") or {"level": 2 if r["brief"]["match_claimed"] else 0, "label": "", "reason": ""}
    word, colour = STATUS[c["level"]]
    head = e.get("headline") or r["brief"]["headline"]
    items = (v.get("candidates") or {}).get("items") or []
    top = items[0] if items else None
    gap = top["score"] - items[1]["score"] if len(items) > 1 else None
    checks = v.get("checks") or []
    kpis = [("Closest reference", escape(top["name"]) if top else "—", ""),
            ("Similarity", f'{top["score"]:.2f}' if top else "—", "cosine, 0–1"),
            ("Margin to runner-up", f"{gap:.2f}" if gap is not None else "—", ""),
            ("Quality checks", f'{sum(x["passed"] for x in checks)}/{len(checks)}' if checks else "—", "passed"),
            ("Confidence", escape(c["label"] or "—"), "")]
    return (f'<section class="result" style="--c:{colour}"><div class="k">{word}</div><div class="hl serif">{escape(head)}</div>'
            f'<p>{escape(e.get("how_sure") or c["reason"])}</p></section>'
            '<div class="kpis">' + "".join(f'<div class="kpi"><span>{k}</span><strong>{val}</strong>'
                                           + (f"<small>{n}</small>" if n else "") + "</div>" for k, val, n in kpis) + "</div>")


def _overlay(v):
    o = v.get("overlay")
    if not o:
        return ""
    series = [("Sample", o["x"], o["sample"], SAMPLE, False)]
    if o.get("reference"):
        series.append((o["reference_name"], o["reference"]["x"], o["reference"]["y"], REFERENCE, False))
    svg = chart(series, "Raman shift (cm⁻¹)", "Relative intensity", h=250,
                points=list(zip(o["peaks"], o["peak_heights"], [str(p) for p in o["peaks"]])))
    legend = (f'<p class="legend"><i style="background:{SAMPLE};margin-left:0"></i>Sample'
              + (f'<i style="background:{REFERENCE}"></i>{escape(o["reference_name"])} (reference)' if o.get("reference") else "") + "</p>")
    cap = (f'<b>Figure 1.</b> Processed sample spectrum overlaid on the best-matching reference, {escape(o["reference_name"])}; '
           'each scaled to its own maximum. Labels mark peaks shared by both spectra.' if o.get("reference")
           else "<b>Figure 1.</b> Processed sample spectrum; labels mark the strongest peaks.")
    return f'<section class="fig">{legend}{svg}<p class="cap">{cap}</p></section>'


REF_TYPE = {"measured": "Measured reference", "synthetic": "Literature-band reference"}


def _ranking(v):
    """Ordered by rank_score (cosine discounted for short overlap), so that score is the bar; cosine and coverage explain it."""
    c = v["candidates"]
    rows = []
    for i, it in enumerate(c["items"]):
        rank = it.get("rank_score", it["score"])
        below = it["score"] < c["threshold"]
        name = ("<b>" + escape(it["name"]) + "</b>") if it["top"] else escape(it["name"])
        kind = f'<br><span style="color:#64748b;font-size:10px">{escape(REF_TYPE.get(it.get("category"), it.get("category") or ""))}</span>'
        rows.append([f'<span class="rk{" top" if it["top"] else ""}">{i + 1}</span>', name + kind,
                     f'<span style="color:{"#94a3b8" if below else "#0f172a"}">{it["score"]:.2f}{"†" if below else ""}</span>',
                     f'{it["coverage"] * 100:.0f}%' if it.get("coverage") is not None else "—",
                     f'<div class="rb"><div class="bar"><i style="width:{min(1, max(0, rank)) * 100:.1f}%;background:'
                     f'{GREEN if it["top"] else "#86d3a8"}"></i></div><span>{rank:.2f}</span></div>'])
    table = _table(["Rank", "Candidate material", "Similarity", "Coverage", "Ranking score"], rows)
    return (table.replace("<table>", '<table class="rank">', 1)
            + '<p class="cap"><b>Similarity</b>: cosine similarity of band shape over the overlap (0 = unrelated, 1 = identical). '
            "<b>Coverage</b>: share of the reference's range that the measurement overlaps. <b>Ranking score</b>: similarity "
            "discounted when coverage is below 70% or the overlap holds under 60% of the sample's signal; candidates are ordered "
            f"by it. † below the {c['threshold']:.2f} similarity required to report a match.</p>")


def _checks(v):
    pill = lambda ok: f'<span class="pill" style="background:{GOOD if ok else CRITICAL}">{"PASS" if ok else "FAIL"}</span>'
    return _table(["Criterion", "Result"], [[f'<b>{escape(c["label"])}</b><br><span style="color:#64748b">{escape(c["detail"])}</span>',
                                             pill(c["passed"])] for c in v["checks"]])
