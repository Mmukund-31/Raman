"""Self-contained HTML report (printable to PDF)."""
from html import escape


def _svg(x, y, title, w=720, h=240, ylabel="", peaks=()):
    lo, hi = min(y), max(y)
    span = (hi - lo) or 1.0
    xs = (x[-1] - x[0]) or 1.0
    pts = " ".join(f"{40 + (a - x[0]) / xs * (w - 50):.1f},{h - 30 - (b - lo) / span * (h - 50):.1f}"
                   for a, b in zip(x[::2], y[::2]))
    return (f'<figure><svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="{escape(title)}">'
            f'<rect width="{w}" height="{h}" fill="#fff" stroke="#ccc"/>'
            f'<polyline fill="none" stroke="#1d4ed8" stroke-width="1.2" points="{pts}"/>'
            f'<text x="{w / 2}" y="{h - 8}" font-size="11" text-anchor="middle">Raman shift (cm⁻¹): {x[0]:.0f}–{x[-1]:.0f}</text>'
            f'<text transform="translate(11 {h / 2}) rotate(-90)" font-size="11" text-anchor="middle">{escape(ylabel)}</text>'
            + "".join(
                f'<text x="{40 + (p["position"] - x[0]) / xs * (w - 50):.1f}" y="{max(10.0, h - 30 - (p["height"] - lo) / span * (h - 50) - 4):.1f}" '
                f'font-size="9" text-anchor="middle" fill="#be123c">{p["position"]:.0f}</text>' for p in peaks) +
            f'</svg><figcaption>{escape(title)}</figcaption></figure>')


def build_report(r: dict) -> str:
    peaks = "".join(f"<tr><td>{p['position']:.1f}</td><td>{p['relative_height']:.2f}</td><td>{p['prominence']:.4g}</td>"
                    f"<td>{'near boundary' if p['near_boundary'] else ''}</td></tr>" for p in r["peaks"])
    matches = "".join(f"<tr><td>{escape(m['name'])}</td><td>{m['score']:.3f}</td><td>{m['coverage'] * 100:.0f}%</td>"
                      f"<td>{escape(m.get('explanation', ''))}</td></tr>" for m in r["matches"])
    meta = r.get("metadata", {})
    prov = r.get("data_provenance", {})
    sp = prov.get("sample", {})
    thr = r.get("quality_thresholds", {})
    thr_rows = "".join(f"<tr><td>{escape(str(k))}</td><td>{escape(str(v))}</td></tr>" for k, v in thr.items())
    ref_rows = "".join(f"<tr><td>{escape(x['reference_id'])}</td><td>{escape(x['category'].upper())}</td><td>{escape(x['source'])}</td></tr>"
                       for x in prov.get("references", []))
    synth = sp.get("category") == "synthetic" or prov.get("references_all_synthetic")
    synth_banner = ('<p class="banner">SYNTHETIC DATA: '
                    + ("the input spectrum is synthetic test data, not a measurement. " if sp.get("category") == "synthetic" else "")
                    + ("The reference library is synthetic (idealised bands). " if prov.get("references_all_synthetic") else "")
                    + "These results demonstrate the software workflow only.</p>") if synth else ""
    warns = "".join(f"<li>{escape(w)}</li>" for w in r["quality_warnings"]) or "<li>None</li>"
    params = "".join(f"<tr><td>{escape(str(k))}</td><td>{escape(str(v))}</td></tr>" for k, v in r["parameters"].items())
    lims = "".join(f"<li>{escape(l)}</li>" for l in r["limitations"])
    verdict = ("INCONCLUSIVE — evidence is inadequate for a match claim." if r["status"] == "inconclusive"
               else "Reference similarities are listed below; they are not a validated identification.")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>RamanReach report – {escape(r['sample_id'])}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:800px;margin:2rem auto;padding:0 1rem;color:#111}}
table{{border-collapse:collapse;width:100%;margin:.5rem 0}}td,th{{border:1px solid #ccc;padding:4px 8px;text-align:left}}
.banner{{background:#fef3c7;border:2px solid #b45309;padding:.6rem 1rem;font-weight:600}}</style></head><body>
<h1>RamanReach analysis report</h1>
<p class="banner">EXPERIMENTAL – NON-DIAGNOSTIC. Not for clinical or safety decisions.</p>
<p><b>Sample:</b> {escape(r['sample_id'])} · <b>Source:</b> {escape(r['source'])} · <br>
<b>Software:</b> RamanReach {r['software_version']} · <b>Timestamp (UTC):</b> {r['timestamp']} · <b>SNR estimate (provisional):</b> {'undefined' if r['snr'] is None else r['snr']}</p>
{synth_banner}
<h2>Coordinates, excitation and calibration</h2><table>
<tr><td>Input coordinate</td><td>{escape(str(meta.get('coordinate_input', 'unknown')))}</td></tr>
<tr><td>Wavelength converted to Raman shift</td><td>{meta.get('wavelength_converted_to_raman_shift', False)}</td></tr>
<tr><td>Excitation wavelength (nm)</td><td>{meta.get('excitation_nm') or 'not provided'} ({escape(str(meta.get('excitation_source', 'not provided')))})</td></tr>
<tr><td>Calibration status</td><td>{escape(str(meta.get('calibration_status', 'not_verified')))} - {escape(str(meta.get('calibration_note', '')))}</td></tr></table>
<h2>Data provenance</h2><p><b>Sample:</b> {escape(str(sp.get('category', 'unknown')).upper())} - {escape(str(sp.get('description', '')))}</p>
<table><tr><th>Reference</th><th>Category</th><th>Source</th></tr>{ref_rows}</table>
<h2>Outcome</h2><p><b>Status: {r['status'].upper()}</b> — {verdict}</p>
<h2>Quality warnings</h2><ul>{warns}</ul>
<h2>Spectra</h2>{_svg(r['x'], r['raw'], 'Raw spectrum (intensity in the units supplied; baseline not removed)', ylabel='Intensity (as supplied)')}{_svg(r['x'], r['processed'], 'Processed spectrum; red numbers are detected peak positions in cm⁻¹', ylabel='Processed intensity (a.u.)', peaks=r['peaks'])}
<h2>Processing parameters</h2><table>{params}</table>
<h2>Detected peaks</h2><table><tr><th>Position (cm⁻¹)</th><th>Relative height</th><th>Prominence</th><th>Flag</th></tr>{peaks}</table>
<h2>Reference comparison (cosine similarity)</h2><table><tr><th>Reference</th><th>Score</th><th>Range coverage</th><th>Explanation</th></tr>{matches}</table>
<p>{escape(r.get("similarity_note", ""))}</p>
<h2>Quality thresholds</h2><table>{thr_rows}</table>
<h2>Limitations</h2><ul>{lims}</ul></body></html>"""


# ---------------------------------------------------------------- research studies (plain-language, sections A-G)

SECTION_TITLES = [("tested", "A. What did we test?"), ("changed", "B. What changed?"), ("graph", "C. What does the graph show?"),
                  ("pca", "D. What did PCA reveal?"), ("model", "E. How did the model perform?"),
                  ("trust", "F. Can we trust this result?"), ("conclusion", "G. What should the user conclude?")]
LEVEL_LABEL = {"observed": "Observed result", "supported": "Supported interpretation",
               "hypothesis": "Hypothesis requiring further testing", "inconclusive": "Inconclusive"}


def _fmt(v):
    return "n/a" if v is None else (f"{v:.4g}" if isinstance(v, float) else escape(str(v)))


def build_research_report(studies: list[dict]) -> str:
    """studies: [{kind, title, result}] where result carries `insights`, `report` and `self_checks`."""
    body = []
    for st in studies:
        r = st["result"]
        dc = r.get("data_class", "unknown")
        banner = ("SIMULATED / SYNTHETIC DATA: not a physical measurement." if dc in ("simulated", "synthetic_example")
                  else "User-declared measured data: origin and calibration not verified by RamanReach.")
        secs = "".join(f"<h3>{t}</h3><p>{escape(r.get('report', {}).get(k, 'Not part of this study.'))}</p>" for k, t in SECTION_TITLES)
        ins = "".join(
            f"<tr><td><b>{escape(LEVEL_LABEL.get(i['level'], i['level']))}</b></td><td>{escape(i['statement'])}"
            + ("<ul>" + "".join(f"<li>{escape(str(e['metric']))}: {_fmt(e['value'])} {escape(e.get('unit') or '')}"
                                + (f" (baseline {_fmt(e['baseline'])})" if e.get("baseline") is not None else "") + "</li>"
                                for e in i["evidence"]) + "</ul>" if i["evidence"] else "")
            + f"</td><td>{escape(i['validation_status'])}</td><td>{escape(' '.join(i['limitations']))}</td></tr>" for i in r.get("insights", []))
        chk = "".join(f"<li>{'PASS' if c.get('passed') else ('FAIL' if c.get('passed') is False else 'n/a')}: {escape(c['name'])}</li>"
                      for c in r.get("self_checks", []))
        body.append(f"<section><h2>{escape(st.get('title', st['kind']))}</h2><div class='b'>{escape(banner)}</div>{secs}"
                    f"<h3>Evidence behind each statement</h3><table><tr><th>Status</th><th>Statement and evidence</th><th>Validation</th>"
                    f"<th>Limitations</th></tr>{ins}</table><h3>Self-checks</h3><ul>{chk or '<li>none</li>'}</ul></section>")
    return ("<!doctype html><html lang='en'><meta charset='utf-8'><title>RamanReach research report</title><style>"
            "body{font:15px/1.5 system-ui;max-width:900px;margin:2rem auto;padding:0 1rem;color:#111}table{border-collapse:collapse;width:100%}"
            "td,th{border:1px solid #ccc;padding:.4rem;vertical-align:top;font-size:13px}.b{border:2px solid #6d28d9;background:#f5f3ff;padding:.5rem;font-weight:600}"
            "h2{border-bottom:1px solid #ccc;margin-top:2rem}</style><h1>RamanReach research report</h1>"
            "<p>Experimental, non-diagnostic research prototype. Statements are generated from computed metrics, never from model confidence. "
            "Simulated results show how the analysis behaves, not how an instrument behaves.</p>" + "".join(body) + "</html>")
