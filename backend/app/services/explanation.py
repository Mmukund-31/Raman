"""Plain-language explanation of a finished report, for readers with no spectroscopy background.

Three pieces, all deterministic:
  evidence(report)  -> numbered facts (E1, E2, ...) copied from computed sections; the ONLY material an LLM may use
  rule_based(report)-> a complete explanation built from those facts with fixed wording (the fallback, and the
                       default when no LLM is configured)
  verify(expl, ev)  -> checks an LLM-written explanation against the evidence: cited ids exist, every number appears in
                       the evidence, no material outside the candidates is named, and an inconclusive result is never
                       presented as an identification. Returns a list of problems (empty = accepted).
"""
import re

from . import pipeline, quality

GLOSSARY = [
    {"term": "Raman spectrum", "plain": "A chart of how a material scatters laser light. Each material gives its own pattern, like a fingerprint."},
    {"term": "Peak", "plain": "A spike in the chart. The positions of the peaks are what identify a material."},
    {"term": "cm⁻¹ (Raman shift)", "plain": "The unit on the chart's horizontal axis; it says where a peak sits."},
    {"term": "Similarity score", "plain": "How closely two fingerprints line up, from 0 (nothing alike) to 1 (identical shape). It is not a probability."},
    {"term": "Reference library", "plain": "The collection of known materials the sample is compared with. Only materials in it can be recognised."},
    {"term": "Signal-to-noise", "plain": "How clearly the peaks stand out from random fluctuation. Low values mean a noisy measurement."},
    {"term": "Inconclusive", "plain": "The evidence was not strong enough to name a material, so the software declines to guess."},
]
_PLAIN_REASONS = [
    ("signal-to-noise", "the measurement is too noisy for the peaks to be trusted"),
    ("could not be estimated", "the noise level could not be measured, so the signal cannot be judged"),
    ("Insufficient overlap", "the measured range overlaps too little with the reference spectra"),
    ("band intensity lies inside", "most of the sample's peaks fall outside the range covered by the closest reference"),
    ("Highest similarity", "no material in the library looks similar enough"),
    ("near-identical scores", "two different materials look almost equally similar, so we cannot choose between them"),
    ("explained better by a mixture", "the spectrum looks like a mixture of two materials, and this tool names only single materials"),
    ("bands were found in the sample", "too few of the closest material's characteristic peaks appear in your spectrum"),
]
NOT_DIAGNOSTIC = "This is a research tool. It is not a certified, medical, legal or safety identification."


def _plain_reason(w: str) -> str:
    return next((p for key, p in _PLAIN_REASONS if key in w), w)


def evidence(report: dict) -> list[dict]:
    a, b, s = report["analysis"], report["brief"], report["sections"]
    ms = s["matching"]["data"]["matches"]
    ok = a["status"] == "ok"
    blocking = [w for w in a["quality_warnings"] if any(k in w for k, _ in _PLAIN_REASONS)]
    ev = []

    def add(label, text, section, **values):
        ev.append({"id": f"E{len(ev) + 1}", "label": label, "text": text, "section": section, "values": values})

    add("Verdict", ("Quality checks passed; a closest match is reported." if ok else
                    "Inconclusive: no material is named. Reasons: " + "; ".join(_plain_reason(w) for w in blocking)),
        "quality", status=a["status"])
    add("Measured range", f"{len(report['sections']['spectrum']['data']['x'])} data points covering {b['metrics'][3]['value']}.",
        "validation")
    pk = sorted(a["peaks"], key=lambda p: -p["relative_height"])[:5]
    if pk:
        add("Peaks", f"{len(a['peaks'])} peaks detected; strongest at " + ", ".join(f"{p['position']:.0f}" for p in pk) + " cm⁻¹.",
            "peaks", n=len(a["peaks"]), positions=[round(p["position"]) for p in pk])
    if ms:
        t = ms[0]
        kind = "a measured reference" if t.get("category") == "measured" else "a SYNTHETIC (simulated) reference"
        src = f" from {t['source'].split(' ')[0]}" if t.get("category") == "measured" and t.get("source") else ""
        add("Closest reference", f"{t['name']} ({kind}{src}), similarity {t['score']:.2f} out of 1.", "matching",
            name=t["name"], score=round(t["score"], 2), category=t.get("category"))
        if len(ms) > 1:
            add("Runner-up", f"{ms[1]['name']}, similarity {ms[1]['score']:.2f}; gap to the closest {t['score'] - ms[1]['score']:.2f}.",
                "matching", name=ms[1]["name"], score=round(ms[1]["score"], 2), gap=round(t["score"] - ms[1]["score"], 2))
        add("Overlap", f"The comparison covered {t['coverage'] * 100:.0f}% of the reference's range and "
                       f"{t.get('sample_signal_in_overlap', 1) * 100:.0f}% of the sample's peak intensity.", "matching")
    mix = a.get("mixture")
    if mix:
        add("Possible mixture", f"A combination of {mix['names'][0]} and {mix['names'][1]} fits the spectrum better than any single "
                                f"material (fit {mix['fit_score']:.2f} against {mix['single_score']:.2f}).", "matching", names=mix["names"])
    snr = a["snr"]
    add("Signal quality", (f"Signal-to-noise about {snr:.0f} (the minimum used is {quality.MIN_SNR:g})." if snr is not None
                           else "Signal-to-noise could not be estimated."), "quality")
    prov = a["data_provenance"]
    cats = prov.get("references_by_category", {})
    add("Library", f"Compared with {prov.get('n_materials', len(ms))} materials ({prov.get('n_reference_spectra', len(ms))} spectra: "
        + ", ".join(f"{n} {c}" for c, n in cats.items()) + ").", "matching")
    if b.get("robustness"):
        add("Robustness", b["robustness"], "sensitivity")
    if report.get("evaluation") and report["evaluation"].get("headline"):
        add("Track record", report["evaluation"]["headline"], "quality")
    if s["pca"]["status"] in ("complete", "partial"):
        add("Several spectra", s["pca"]["summary"].split(". PCA is")[0] + ".", "pca")
    notes = [w for w in a["quality_warnings"] if w not in blocking and not w.startswith(("Excitation wavelength not provided",))][:4]
    if notes:
        add("Processing notes", " ".join(notes), "validation")
    fm = report.get("inputs", {}).get("file_metadata") or {}
    if fm.get("name"):
        add("Label inside the file", f"The file itself names the sample '{fm['name']}' ({fm.get('format', 'file')}). This label was "
                                     "not used for matching and is not verified.", "validation", name=fm["name"])
    add("Calibration", "The instrument's wavelength calibration could not be checked by this software.", "quality")
    steps = [x for x in report["conclusion"]["next_steps"] if not x.startswith("To enable")][:4]
    if steps:
        add("Suggested next steps", " ".join(steps), "conclusion")
    return ev


def rule_based(report: dict) -> dict:
    ev = evidence(report)
    by = {e["label"]: e for e in ev}
    a = report["analysis"]
    ms = report["sections"]["matching"]["data"]["matches"]
    ok = a["status"] == "ok"
    top = ms[0] if ms else None
    synth_top = bool(top) and top.get("category") != "measured"
    ids = lambda *labels: [by[l]["id"] for l in labels if l in by]

    if ok and top and not synth_top:
        headline = f"Your sample's fingerprint looks most like {top['name']}."
    elif ok and top:
        headline = (f"Your spectrum looks most like the {top['name']} demo reference, but that reference is simulated, "
                    "so this is not a real identification.")
    else:
        headline = "We could not confidently tell what this sample is."
    found = []
    if "Peaks" in by:
        found.append({"text": f"We found {by['Peaks']['values']['n']} peaks, the material's 'fingerprint'. The strongest sit at "
                              + ", ".join(str(p) for p in by["Peaks"]["values"]["positions"][:3]) + " cm⁻¹.", "evidence": ids("Peaks")})
    if top and ok:
        t = f"This fingerprint lines up with {top['name']} with a similarity of {top['score']:.2f} out of 1"
        t += f", clearly ahead of the next closest material, {ms[1]['name']} ({ms[1]['score']:.2f})." if len(ms) > 1 else "."
        found.append({"text": t, "evidence": ids("Closest reference", "Runner-up")})
    elif top:
        reasons = [w for w in a["quality_warnings"] if any(k in w for k, _ in _PLAIN_REASONS)]
        found.append({"text": f"The closest material in our library was {top['name']} (similarity {top['score']:.2f}), but we do not "
                              f"name it because {_plain_reason(reasons[0]) if reasons else 'the checks were not met'}.",
                      "evidence": ids("Closest reference", "Verdict")})
        if "Possible mixture" in by:
            n1, n2 = by["Possible mixture"]["values"]["names"]
            found.append({"text": f"Your sample may contain both {n1} and {n2}: together they match the spectrum better than either "
                                  "one alone.", "evidence": ids("Possible mixture")})
    sens = report["sections"]["sensitivity"]
    if "Robustness" in by and sens["status"] == "complete":
        d = sens["data"]
        if d["top1_changed_at"]:
            t = (f"When we shifted the chart sideways to mimic a calibration error, the best match stayed the same up to "
                 f"±{d['stable_within_cm1']:g} cm⁻¹ but changed at {d['top1_changed_at'][0]:+g} cm⁻¹.")
        else:
            t = (f"When we shifted the chart sideways by up to ±{d['tested_range_cm1']:g} cm⁻¹ to mimic a calibration error, "
                 "the best match stayed the same.")
        found.append({"text": t, "evidence": ids("Robustness")})
    if "Several spectra" in by:
        found.append({"text": by["Several spectra"]["text"], "evidence": ids("Several spectra")})

    if ok and not synth_top:
        sure = "Fairly confident, within the limits below: the match passed every quality check."
    elif ok:
        sure = "Not applicable: the closest reference is simulated, so the result only shows how the software works."
    else:
        sure = "Not confident. The software prefers to say 'we can't tell' rather than guess."
    if "Track record" in by:
        sure += " " + by["Track record"]["text"]
    not_mean = [NOT_DIAGNOSTIC,
                f"Only the {a['data_provenance'].get('n_materials', len(ms))} materials in the library can be recognised. "
                "A sample made of something else may still look closest to one of them.",
                "A mixture of materials, a coating, or a container (glass, plastic bag) can change the fingerprint.",
                "The similarity score describes how alike the shapes are; it is not the chance that the answer is right."]
    if "Label inside the file" in by:
        not_mean.append("The name written inside your file was not used and has not been checked.")
    steps = [s for s in report["conclusion"]["next_steps"] if not s.startswith("To enable")][:3]
    return {"source": "rule_based", "headline": headline, "what_we_found": found, "how_sure": sure,
            "what_this_does_not_mean": not_mean, "next_steps": steps, "glossary": GLOSSARY, "evidence": ev,
            "note": "Standard summary written from fixed templates using only the computed results."}


# ---------------------------------------------------------------- verification of LLM-written text

_NUM = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:[.,]\d+)?")
_ID_CLAIM = re.compile(r"\b(identified as|is identified|confirmed|definitely|certainly|we (?:found|know) (?:it|this) (?:is|to be)|"
                       r"the sample is (?:made of|composed of)?\s*[A-Z])", re.I)
_FORBIDDEN = re.compile(r"\b(diagnos\w*|safe to (?:eat|use|drink|handle)|toxic|non-toxic|edible|authentic|counterfeit|fake|genuine)\b", re.I)


def _numbers(text):
    """(value, decimals) for every number written in the text."""
    out = []
    for m in _NUM.findall(text):
        t = m.replace(",", ".")
        try:
            out.append((float(t), len(t.split(".")[1]) if "." in t else 0))
        except ValueError:
            pass
    return out


def _allowed_numbers(ev):
    return [v for e in ev for v, _ in _numbers(e["text"])]


def _supported(n, dec, allowed):
    """A written number is supported when some evidence value, rounded to the precision it is written with, equals it
    (also as a percentage of a 0-1 value). 99.9 is NOT supported by 1.00; 100 is."""
    for v in allowed:
        if round(v, dec) == n or round(-v, dec) == n or (abs(v) <= 1 and round(v * 100, dec) == n):
            return True
    return False


def _texts(expl):
    yield expl.get("headline", "")
    for f in expl.get("what_we_found", []):
        yield f.get("text", "")
    yield expl.get("how_sure", "")
    yield from expl.get("what_this_does_not_mean", [])
    yield from expl.get("next_steps", [])


def verify(expl: dict, ev: list[dict], report: dict) -> list[str]:
    problems = []
    ids = {e["id"] for e in ev}
    for f in expl.get("what_we_found", []):
        if not f.get("evidence"):
            problems.append(f"Finding has no evidence: '{f.get('text', '')[:60]}'")
        bad = [i for i in f.get("evidence", []) if i not in ids]
        if bad:
            problems.append(f"Unknown evidence ids {bad}")
    allowed = _allowed_numbers(ev)
    for t in _texts(expl):
        for n, dec in _numbers(t):
            if abs(n) <= 12 and dec == 0:
                continue  # small counts ("three peaks", "1 out of") are fine
            if not _supported(n, dec, allowed):
                problems.append(f"Number {n:g} does not appear in the evidence: '{t[:80]}'")
        if _FORBIDDEN.search(t) and not any(_FORBIDDEN.search(e["text"]) for e in ev):
            problems.append(f"Claim outside the scope of the evidence: '{t[:80]}'")
    named = {e["values"].get("name") for e in ev if e["values"].get("name")}
    named |= {n for e in ev for n in e["values"].get("names", [])}
    lib_names = {r["name"] for r in pipeline.load_references("all")}
    all_text = " ".join(_texts(expl))
    for nm in sorted(lib_names - named):
        if len(nm) > 3 and re.search(rf"\b{re.escape(nm)}\b", all_text, re.I):
            problems.append(f"Names '{nm}', which is not among the candidates in the evidence")
    if report["analysis"]["status"] != "ok":
        head = expl.get("headline", "")
        if not re.search(r"could not|couldn't|can't|cannot|not (?:able|confident|sure|possible)|unclear|inconclusive|no (?:reliable|clear|confident)", head, re.I):
            problems.append("The result is inconclusive but the headline does not say so")
        if _ID_CLAIM.search(all_text):
            problems.append("The result is inconclusive but the text presents an identification")
    return problems
