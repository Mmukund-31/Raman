"""Self-contained HTML report: a one-page, picture-first summary, then a technical page. Print-friendly, so the
browser's "Save as PDF" gives a two-page PDF."""
import math
from datetime import datetime
from html import escape

ACCENT, PEAK, BASE = "#1f45b8", "#52514e", "#d97706"


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


SAMPLE, REFERENCE, MUTED_BAR = "#2a78d6", "#eb6834", "#c3c2b7"  # validated pair (dataviz validator)
GOOD, CRITICAL, WARN = "#0ca30c", "#d03b3b", "#fab219"

CSS = """*{box-sizing:border-box;-webkit-print-color-adjust:exact;print-color-adjust:exact}
body{font:14px/1.55 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;color:#0f172a;background:#fff;max-width:820px;margin:0 auto;padding:32px 28px}
.top{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:1px solid #e2e8f0;padding-bottom:10px}
h1{font-size:20px;margin:0}.meta{font-size:11.5px;color:#64748b;text-align:right;line-height:1.5}
h2{font-size:15px;margin:24px 0 8px;color:#0f172a}h3{font-size:13px;margin:16px 0 6px}
.answer{margin-top:18px;border-radius:14px;padding:18px 20px;display:flex;gap:16px;align-items:flex-start}
.answer .ic{flex:none;width:46px;height:46px;border-radius:50%;color:#fff;font-size:22px;font-weight:700;display:flex;align-items:center;justify-content:center}
.answer .w{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#52514e;font-weight:600}
.answer .hl{font-size:19px;font-weight:600;margin:2px 0 10px;line-height:1.3}
.meter{display:grid;grid-template-columns:repeat(3,90px);gap:4px}.meter div{height:7px;border-radius:4px;background:#fff;border:1px solid #e2e8f0}
.meter span{display:block;font-size:10.5px;color:#64748b;margin-top:2px}.meter b{color:#0f172a}
.legend{font-size:12px;color:#52514e;margin:0 0 4px}.legend i{display:inline-block;width:14px;height:3px;border-radius:2px;vertical-align:middle;margin:0 5px 0 12px}
.cap{font-size:12px;color:#64748b;margin:4px 0 0}.two{display:grid;grid-template-columns:1fr 1fr;gap:28px}
.bar{margin:0 0 9px}.bar .lab{display:flex;justify-content:space-between;font-size:12.5px}.bar .tr{position:relative;height:9px;border-radius:5px;background:#f1f5f9;margin-top:3px}
.bar .fill{height:100%;border-radius:5px}.bar .th{position:absolute;top:-3px;bottom:-3px;width:1px;background:#52514e}
.chk{display:flex;gap:9px;margin:0 0 8px;font-size:12.5px}.chk .d{flex:none;width:17px;height:17px;border-radius:50%;color:#fff;font-size:10px;font-weight:700;display:flex;align-items:center;justify-content:center;margin-top:1px}
.chk small{display:block;color:#64748b;font-size:11.5px}
ul{margin:0;padding-left:17px}li{margin:3px 0}
.tech{break-before:page;margin-top:34px;border-top:1px solid #e2e8f0;padding-top:6px}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.kpi{border:1px solid #e2e8f0;border-radius:8px;padding:6px 9px}
.kpi span{display:block;font-size:10px;color:#64748b}.kpi strong{font-size:15px}.kpi small{display:block;font-size:9px;color:#94a3b8}
table{border-collapse:collapse;width:100%;font-size:11.5px}th{text-align:left;font-weight:600;color:#475569;border-bottom:1px solid #cbd5e1;padding:4px 6px}
td{border-bottom:1px solid #f1f5f9;padding:4px 6px}.facts{font-size:11px;color:#475569}.tk{font-size:9.5px;fill:#64748b}.ax{font-size:10.5px;fill:#334155}
.pk{font-size:9.5px;fill:#52514e}.foot{margin-top:20px;border-top:1px solid #e2e8f0;padding-top:8px;font-size:10.5px;color:#64748b}
@media (max-width:640px){.two,.kpis{grid-template-columns:1fr}}
@media print{body{padding:0}section,table,svg,.answer{break-inside:avoid}@page{margin:14mm}}"""


def build(r: dict) -> str:
    b = r["brief"]
    v = r.get("visual") or {}
    e = r.get("explanation") or {}
    sp = r["sections"]["spectrum"]["data"]
    when = datetime.fromisoformat(r["generated_at"]).strftime("%d %b %Y, %H:%M UTC")
    found = [f["text"] for f in e.get("what_we_found", [])][:3] or b["findings"]
    nxt = (e.get("next_steps") or b["recommendations"])[:3]
    top = sorted(sp["peaks"], key=lambda p: -p["relative_height"])[:10]
    tech_fig = chart([("Processed", sp["x"], sp["processed"], SAMPLE, False)], "Raman shift (cm⁻¹)", "Processed intensity (a.u.)",
                     h=220, points=[(p["position"], p["height"], f'{p["position"]:.0f}') for p in top])
    peaks = _table(["Position (cm⁻¹)", "Rel. intensity", "Tentative region"], [
        [f'{p["position"]:.0f}', f'{p["relative_height"]:.2f}', escape(p["assignment"] or "—")] for p in b["peaks"]])
    kpis = "".join(f'<div class="kpi"><span>{escape(m["label"])}</span><strong>{escape(m["value"])}</strong>'
                   + (f'<small>{escape(m["note"])}</small>' if m.get("note") else "") + "</div>" for m in b["metrics"])
    lims = b["limitations"] + ([r["evaluation"]["headline"]] if (r.get("evaluation") or {}).get("headline") else [])
    facts = "".join(f'<li>{escape(x["id"])} {escape(x["label"])}: {escape(x["text"])}</li>' for x in e.get("evidence", []))
    np_ = "; ".join(f'{x["title"]} ({x["reason"]})' for x in b["not_performed"])
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>Spectrum analysis – {escape(r["sample_id"])}</title><style>{CSS}</style></head><body>'
            f'<div class="top"><h1>Spectrum analysis report</h1><div class="meta">Sample <b>{escape(r["sample_id"])}</b><br>'
            f'{escape(when)} · {escape(b["report_id"])}</div></div>'
            + _answer(r, v, e)
            + _overlay(v)
            + (f'<section class="two"><div><h2>How close were the candidates?</h2>{_bars(v)}</div>'
               f'<div><h2>Checks we ran</h2>{_checks(v)}</div></section>' if v else "")
            + f'<section class="two"><div><h2>What this means</h2>{_ul(found)}</div><div><h2>What to do next</h2>{_ul(nxt)}</div></section>'
            f'<div class="foot">Research use only, not for medical, legal or safety decisions. A similarity score is not a probability; '
            f'only materials in the reference library can be recognised. RamanReach {escape(str(r["software_version"]))}.</div>'
            f'<section class="tech"><h2>Technical details</h2><div class="kpis">{kpis}</div>'
            f'<h3>Processed spectrum with detected peaks</h3>{tech_fig}'
            f'<div class="two"><div><h3>Principal peaks</h3>{peaks}<p class="cap">Regions are tentative textbook ranges, not assignments.</p></div>'
            f'<div><h3>Reliability notes</h3>{_ul(lims)}</div></div>'
            + (f'<h3>Evidence behind the summary</h3><ul class="facts">{facts}</ul>' if facts else "")
            + f'<p class="cap"><b>Methods.</b> {escape(b["methods"])}'
            + (f' <b>Not performed:</b> {escape(np_)}.' if np_ else "")
            + '</p></section></body></html>')


def _answer(r, v, e):
    c = v.get("confidence") or {"level": 2 if r["brief"]["match_claimed"] else 0, "label": "", "reason": ""}
    lvl = c["level"]
    word, icon, colour, bg = (("Match found", "&#10003;", GOOD, "#ecfdf5") if lvl >= 2 else
                              ("Demo result", "i", WARN, "#fffbeb") if lvl == 1 else ("No clear match", "?", "#52514e", "#f8fafc"))
    head = e.get("headline") or r["brief"]["headline"]
    if lvl == 1:
        meter = f'<p class="cap" style="color:#52514e">{escape(c["reason"])}</p>'
    else:
        filled = {3: 3, 2: 2, 0: 1}[lvl]
        steps = ["Can't tell", "Likely", "Confident"]
        fill = "#898781" if filled == 1 else GOOD
        meter = ('<div class="meter">' + "".join(
            f'<div style="{f"background:{fill};border-color:{fill}" if i < filled else ""}"></div>' for i in range(3)) + "</div>"
            '<div class="meter">' + "".join(f'<span>{"<b>" + escape(s) + "</b>" if i == filled - 1 else escape(s)}</span>' for i, s in enumerate(steps))
            + f'</div><p class="cap" style="color:#52514e">{escape(c["reason"])}</p>')
    return (f'<section class="answer" style="background:{bg}"><div class="ic" style="background:{colour}">{icon}</div><div>'
            f'<div class="w">{word}</div><div class="hl">{escape(head)}</div>'
            f'<div style="font-size:12.5px;margin-bottom:4px">How sure are we? <b>{escape(c["label"])}</b></div>{meter}</div></section>')


def _overlay(v):
    o = v.get("overlay")
    if not o:
        return ""
    series = [("Your sample", o["x"], o["sample"], SAMPLE, False)]
    if o.get("reference"):
        series.append((o["reference_name"], o["reference"]["x"], o["reference"]["y"], REFERENCE, False))
    svg = chart(series, "Raman shift (cm⁻¹): position of each peak", "Relative strength", h=250,
                points=list(zip(o["peaks"], o["peak_heights"], [str(p) for p in o["peaks"]])))
    legend = (f'<p class="legend"><i style="background:{SAMPLE};margin-left:0"></i>Your sample'
              + (f'<i style="background:{REFERENCE}"></i>{escape(o["reference_name"])} (reference)' if o.get("reference") else "") + "</p>")
    closest = "" if v["candidates"]["named"] else "the closest material, "
    title = f'Your spectrum next to {closest}{escape(o["reference_name"])}' if o.get("reference") else "Your spectrum"
    return (f'<section><h2>{title}</h2>{legend}{svg}<p class="cap">Each spike (“peak”) is part of the material’s fingerprint.'
            + (" The more the blue and orange peaks line up, the better the match." if o.get("reference") else "")
            + " Labelled numbers mark peak positions.</p></section>")


def _bars(v):
    c = v["candidates"]
    rows = []
    for it in c["items"]:
        colour = SAMPLE if it["top"] and c["named"] else MUTED_BAR
        rows.append(f'<div class="bar"><div class="lab"><span>{"<b>" if it["top"] else ""}{escape(it["name"])}{"</b>" if it["top"] else ""}'
                    + (' <small style="color:#94a3b8">(demo)</small>' if it.get("category") == "synthetic" else "")
                    + f'</span><span>{it["score"]:.2f}</span></div><div class="tr"><div class="fill" style="width:{min(1, it["score"]) * 100:.1f}%;'
                    f'background:{colour}"></div><div class="th" style="left:{c["threshold"] * 100:.1f}%"></div></div></div>')
    return ("".join(rows) + f'<p class="cap">0 = nothing alike, 1 = identical. The thin line at {c["threshold"]:.2f} is the minimum '
            "needed before a material is named.</p>")


def _checks(v):
    return "".join(f'<div class="chk"><span class="d" style="background:{GOOD if c["passed"] else CRITICAL}">{"&#10003;" if c["passed"] else "&#10005;"}</span>'
                   f'<span><b>{escape(c["label"])}</b> <span style="position:absolute;left:-9999px">{"passed" if c["passed"] else "not passed"}</span>'
                   f'<small>{escape(c["detail"])}</small></span></div>' for c in v["checks"])
