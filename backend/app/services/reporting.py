"""Self-contained HTML report (printable to PDF)."""
from html import escape


def _svg(x, y, title, w=720, h=240):
    lo, hi = min(y), max(y)
    span = (hi - lo) or 1.0
    xs = (x[-1] - x[0]) or 1.0
    pts = " ".join(f"{40 + (a - x[0]) / xs * (w - 50):.1f},{h - 30 - (b - lo) / span * (h - 50):.1f}"
                   for a, b in zip(x[::2], y[::2]))
    return (f'<figure><svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="{escape(title)}">'
            f'<rect width="{w}" height="{h}" fill="#fff" stroke="#ccc"/>'
            f'<polyline fill="none" stroke="#1d4ed8" stroke-width="1.2" points="{pts}"/>'
            f'<text x="{w / 2}" y="{h - 8}" font-size="11" text-anchor="middle">Raman shift (cm⁻¹): {x[0]:.0f}–{x[-1]:.0f}</text>'
            f'</svg><figcaption>{escape(title)}</figcaption></figure>')


def build_report(r: dict) -> str:
    peaks = "".join(f"<tr><td>{p['position']:.1f}</td><td>{p['relative_height']:.2f}</td><td>{p['prominence']:.4g}</td>"
                    f"<td>{'near boundary' if p['near_boundary'] else ''}</td></tr>" for p in r["peaks"])
    matches = "".join(f"<tr><td>{escape(m['name'])}</td><td>{m['score']:.3f}</td><td>{m['coverage'] * 100:.0f}%</td></tr>"
                      for m in r["matches"])
    warns = "".join(f"<li>{escape(w)}</li>" for w in r["quality_warnings"]) or "<li>None</li>"
    params = "".join(f"<tr><td>{escape(str(k))}</td><td>{escape(str(v))}</td></tr>" for k, v in r["parameters"].items())
    lims = "".join(f"<li>{escape(l)}</li>" for l in r["limitations"])
    verdict = ("INCONCLUSIVE — evidence is inadequate for a match claim." if r["status"] == "inconclusive"
               else "Candidate matches below (similarity only; not a validated identification).")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>RamanReach report – {escape(r['sample_id'])}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:800px;margin:2rem auto;padding:0 1rem;color:#111}}
table{{border-collapse:collapse;width:100%;margin:.5rem 0}}td,th{{border:1px solid #ccc;padding:4px 8px;text-align:left}}
.banner{{background:#fef3c7;border:2px solid #b45309;padding:.6rem 1rem;font-weight:600}}</style></head><body>
<h1>RamanReach analysis report</h1>
<p class="banner">EXPERIMENTAL – NON-DIAGNOSTIC. Not for clinical or safety decisions.</p>
<p><b>Sample:</b> {escape(r['sample_id'])} · <b>Source:</b> {escape(r['source'])} · <b>Excitation:</b> {r['excitation_nm'] or 'not provided'} nm<br>
<b>Software:</b> RamanReach {r['software_version']} · <b>Timestamp (UTC):</b> {r['timestamp']} · <b>SNR estimate:</b> {r['snr']}</p>
<h2>Outcome</h2><p><b>Status: {r['status'].upper()}</b> — {verdict}</p>
<h2>Quality warnings</h2><ul>{warns}</ul>
<h2>Spectra</h2>{_svg(r['x'], r['raw'], 'Raw spectrum')}{_svg(r['x'], r['processed'], 'Processed spectrum')}
<h2>Processing parameters</h2><table>{params}</table>
<h2>Detected peaks</h2><table><tr><th>Position (cm⁻¹)</th><th>Relative height</th><th>Prominence</th><th>Flag</th></tr>{peaks}</table>
<h2>Reference comparison (cosine similarity)</h2><table><tr><th>Reference</th><th>Score</th><th>Range coverage</th></tr>{matches}</table>
<h2>Limitations</h2><ul>{lims}</ul></body></html>"""
