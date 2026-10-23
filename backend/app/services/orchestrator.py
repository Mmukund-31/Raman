"""Unified analysis: one uploaded spectrum (plus optional extras) -> every analysis the data can legitimately support.

`run()` is a generator of progress events so the HTTP layer can stream genuine stage completion. Each optional analysis
reuses the existing lab service unchanged; when the data cannot support it, its section is marked `insufficient_data`
with the reason and what would be needed. Nothing is filled in with simulated stand-ins for the user's data.
"""
import math
from datetime import datetime, timezone

import numpy as np

from . import dataset_builder, evaluation_real, experiment_conditions as ec, insight_generation as ig, matching
from . import pca_analysis, pipeline, quality, visual
from . import wavenumber_sensitivity as ws
from .formats import parse_any
from .validation import ValidationError

REPORT_VERSION = "1.0"
COMPLETE, PARTIAL, INSUFFICIENT, ERROR = "complete", "partial", "insufficient_data", "error"
MAX_EXTRAS = 10
PCA_MIN_SPECTRA = 3  # run_pca's own minimum; below MIN_SPECTRA_WARN it adds its own reliability warning
STAGES = [
    ("validate", "Reading and validating the file"),
    ("process", "Processing spectrum, detecting peaks and matching references"),
    ("conditions", "Reviewing experimental conditions"),
    ("sensitivity", "Running wavenumber sensitivity tests"),
    ("pca", "Comparing spectra with PCA"),
    ("models", "Checking model benchmark and translation requirements"),
    ("report", "Assembling the final report"),
    ("explain", "Writing the plain-language summary"),
]
ORIGINS = {
    "measured": ("measured", "Declared by the user as a real instrument measurement; origin and calibration not verified."),
    "synthetic": ("synthetic", "Declared by the user as synthetic or simulated data, not a physical measurement."),
    "unknown": ("user_supplied", "Uploaded by the user; origin (measured or synthetic) was not declared and calibration is not verified."),
}
# Broad textbook correlation-chart regions. Ranges overlap and depend on the molecule; they are hints, never assignments.
BAND_REGIONS = [
    (400, 700, "skeletal bending / ring deformation modes"),
    (800, 950, "C-C and C-O-C skeletal stretching"),
    (990, 1010, "aromatic ring breathing (e.g. monosubstituted benzene)"),
    (1000, 1200, "C-C, C-O and C-N stretching"),
    (1250, 1350, "CH2 twisting/wagging, amide III"),
    (1430, 1470, "CH2/CH3 deformation"),
    (1550, 1620, "aromatic C=C stretching"),
    (1620, 1680, "C=C stretching, amide I"),
    (1680, 1800, "C=O stretching"),
    (2100, 2260, "C≡C or C≡N stretching"),
    (2800, 3000, "aliphatic C-H stretching"),
    (3000, 3100, "aromatic / olefinic C-H stretching"),
    (3200, 3600, "O-H / N-H stretching (usually weak in Raman)"),
]
BAND_NOTE = ("Region hints come from general Raman correlation charts. Ranges overlap and shift with molecular environment, "
             "so they suggest where to look, not what the sample contains.")
METADATA_LABELS = {"temperature_K": ("Temperature", "K"), "excitation_nm": ("Excitation wavelength", "nm"),
                   "laser_power_mW": ("Laser power", "mW"), "exposure_s": ("Exposure time", "s"),
                   "incidence_angle_deg": ("Incidence angle", "°"), "collection_angle_deg": ("Collection angle", "°"),
                   "geometry": ("Geometry", ""), "instrument": ("Instrument", ""), "spot_diameter_um": ("Spot diameter", "µm")}


class AnalysisFailed(Exception):
    def __init__(self, stage, message):
        super().__init__(message)
        self.stage = stage


def _section(title, status, summary, data=None, reason=None, requirements=None, data_class=None, technical=None):
    return {"title": title, "status": status, "summary": summary, "reason": reason, "requirements": requirements or [],
            "data": data or {}, "data_class": data_class, "technical": technical or {}}


def clean(o):
    """JSON-safe copy: numpy scalars to Python, non-finite floats to None (JSON has no NaN)."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return clean(o.tolist())
    if isinstance(o, np.generic):
        o = o.item()
    if isinstance(o, float) and not math.isfinite(o):
        return None
    return o


def example_truth(sample_id: str) -> str | None:
    """Bundled synthetic examples are generated from a known reference; same rule as the research labs."""
    guess = sample_id.replace("demo_", "").replace("_synthetic", "")
    return guess if guess in {r["id"] for r in pipeline.load_references()} else None


# ---------------------------------------------------------------- section builders (pure; from computed outputs only)

def _validation_section(spec, extras_ok, extras_failed):
    step = float(np.median(np.diff(spec.x)))
    data = {"points": int(spec.x.size), "range_cm1": [float(spec.x[0]), float(spec.x[-1])], "median_step_cm1": step,
            "coordinate_input": spec.coordinate_input, "converted_from_wavelength": spec.converted,
            "warnings": spec.warnings, "additional_spectra": [{"name": e["name"], "points": int(e["x"].size),
                                                               "range_cm1": [float(e["x"][0]), float(e["x"][-1])]} for e in extras_ok],
            "rejected_additional_spectra": extras_failed, "file_metadata": spec.meta}
    fmt = spec.meta.get("format")
    summary = (f"The file{f' ({fmt})' if fmt else ''} passed validation: {spec.x.size} points from {spec.x[0]:.0f} to {spec.x[-1]:.0f} cm⁻¹ "
               f"(median spacing {step:.2g} cm⁻¹).")
    if extras_failed:
        summary += f" {len(extras_failed)} additional file(s) were rejected and left out."
    return _section("Spectrum validation", PARTIAL if extras_failed else COMPLETE, summary, data)


def _peak_section(a):
    near = {}
    for m in a["matches"]:
        for pair in m["peak_agreement"]["matched"]:
            near.setdefault(pair["sample"], []).append(m["name"])
    rows = []
    for p in sorted(a["peaks"], key=lambda p: p["position"]):
        regions = [lbl for lo, hi, lbl in BAND_REGIONS if lo <= p["position"] <= hi]
        rows.append({**p, "region_hints": regions, "near_reference_bands": near.get(p["position"], [])})
    if not rows:
        return _section("Peak analysis", COMPLETE, "No peaks exceeded the prominence threshold.",
                        {"peaks": [], "band_note": BAND_NOTE, "tolerance_cm1": matching.PEAK_TOLERANCE})
    strongest = max(rows, key=lambda p: p["relative_height"])
    edge = sum(p["near_boundary"] for p in rows)
    summary = (f"{len(rows)} peak(s) detected; the strongest is at {strongest['position']:.0f} cm⁻¹."
               + (f" {edge} lie near the edge of the measured range and may be truncated." if edge else ""))
    return _section("Peak analysis", COMPLETE, summary,
                    {"peaks": rows, "band_note": BAND_NOTE, "tolerance_cm1": matching.PEAK_TOLERANCE,
                     "prominence_frac": a["parameters"]["peak_prominence_frac"]})


def _matching_section(a):
    ms = a["matches"]
    synth = a["data_provenance"]["references_all_synthetic"]
    if a["status"] == "inconclusive":
        summary = ("The reference comparison is inconclusive: " + (a["quality_warnings"][0] if a["quality_warnings"] else "")
                   + " Scores are still listed for transparency, but no match is claimed.")
    else:
        summary = (f"Highest band-shape similarity: {ms[0]['name']} ({ms[0]['score']:.2f}), next {ms[1]['name']} "
                   f"({ms[1]['score']:.2f}). This ranks similarity; it is not a probability of identification.")
    if synth:
        summary += " References are idealised literature-band spectra."
    return _section("Reference matching", COMPLETE, summary,
                    {"matches": ms, "similarity_note": a["similarity_note"], "claim_allowed": a["status"] == "ok",
                     "references_all_synthetic": synth})


def _conditions_section(meta, spec, cmp_res, cmp_err):
    recorded = {k: meta[k] for k in METADATA_LABELS if meta.get(k) is not None}
    missing = [k for k in METADATA_LABELS if meta.get(k) is None]
    data = {"metadata": meta, "recorded": recorded, "missing": missing, "labels": METADATA_LABELS,
            "power_density_mW_per_um2": meta.get("power_density_mW_per_um2"), "laser_color": meta.get("laser_color")}
    if meta.get("excitation_nm"):
        try:
            data["excitation"] = ec.excitation_info(meta["excitation_nm"], float(spec.x[0]), float(spec.x[-1]))
        except ValueError as e:
            data["excitation_error"] = str(e)
    req = []
    if cmp_res is not None:
        data["comparison"] = cmp_res
        status = COMPLETE
        summary = f"{len(recorded)} of {len(METADATA_LABELS)} condition fields recorded. Compared with {len(cmp_res['experiments'])} additional spectrum/spectra."
    else:
        status = PARTIAL
        summary = f"{len(recorded)} of {len(METADATA_LABELS)} condition fields recorded."
        req.append("Upload a second spectrum of the same sample under a different, recorded condition to compare conditions.")
        if cmp_err:
            data["comparison_error"] = cmp_err
    if missing:
        summary += " Missing: " + ", ".join(METADATA_LABELS[k][0].lower() for k in missing) + "."
    reason = None if cmp_res is not None else (cmp_err or "Only one spectrum was provided, so no condition comparison is possible; metadata is reported as recorded.")
    return _section("Experimental conditions", status, summary, data, reason, req)


def _sensitivity_section(s):
    rows = [r for r in s["rows"] if "error" not in r]
    base_top = s["baseline"]["top1"]
    neutral = s["neutral_level"]
    stable = None  # largest |shift| up to which every tested level kept the unperturbed top-ranked reference
    for lv in sorted({abs(r["level"] - neutral) for r in rows}):
        if all(r["top1"] == base_top for r in rows if abs(r["level"] - neutral) <= lv):
            stable = lv
        else:
            break
    changed = sorted({r["level"] for r in rows if r["top1"] != base_top}, key=abs)
    trimmed = [{k: v for k, v in r.items() if k not in ("x", "raw", "record")} | {"same_top1": r["top1"] == base_top}
               for r in s["rows"]]
    tested = max(abs(r["level"]) for r in rows) if rows else 0
    if changed:
        summary = (f"The top-ranked reference stayed '{base_top}' for simulated axis shifts up to ±{stable:g} cm⁻¹ and changed at "
                   f"{changed[0]:+g} cm⁻¹.")
    else:
        summary = f"The top-ranked reference stayed '{base_top}' across all tested axis shifts (±{tested:g} cm⁻¹)."
    summary += " These are simulated shifts of your spectrum; they test the analysis, not your instrument."
    data = {k: s[k] for k in ("kind", "label", "level_unit", "neutral_level", "truth", "baseline", "baseline_peaks",
                              "baseline_processed", "baseline_x", "first_failure", "reference_pca", "distinction_note",
                              "limitations", "self_checks")}
    data.update(rows=trimmed, stable_within_cm1=stable, top1_changed_at=changed, tested_range_cm1=tested,
                insights=ig.from_sweep(s))
    return _section("Wavenumber sensitivity", COMPLETE, summary, data, data_class="simulated")


def _pca_section(primary, extras, options, primary_label):
    n = 1 + len(extras)
    if n < PCA_MIN_SPECTRA:
        return _section("PCA", INSUFFICIENT, "Insufficient data: PCA needs several spectra to compare.",
                        reason=f"PCA describes variation across a set of spectra. {n} spectrum/spectra were provided; at least "
                               f"{PCA_MIN_SPECTRA} are required, and {pca_analysis.MIN_SPECTRA_WARN}+ for stable structure.",
                        requirements=["Upload additional spectra (replicates, related samples or other conditions) with the main file.",
                                      "Optionally label each spectrum so group structure can be assessed."])
    spectra = [(primary["x"], primary["y"])] + [(e["x"], e["y"]) for e in extras]
    names = [primary["name"]] + [e["name"] for e in extras]
    labels = [primary_label or "unlabelled"] + [e.get("label") or "unlabelled" for e in extras]
    grid, M, notes = pca_analysis.align_to_common_grid(spectra)
    Xp = dataset_builder.preprocess_matrix(M, options)
    meta = [{"spectrum_id": nm, "specimen_id": nm, "material": lb, "condition": "as supplied", "role": "main" if i == 0 else "additional"}
            for i, (nm, lb) in enumerate(zip(names, labels))]
    factors = ("material",) if len(set(labels)) >= 2 else ()
    res = pca_analysis.run_pca(grid, Xp, meta, min(5, n - 1), "none", factors)
    res["data_class"] = "user_supplied"
    res["alignment_notes"] = notes
    res["insights"] = ig.from_pca(res)
    evr = res["explained_variance_ratio"]
    summary = (f"PCA on {n} spectra: PC1 explains {100 * evr[0]:.0f}% and PC2 {100 * evr[1]:.0f}% of the variance"
               if len(evr) > 1 else f"PCA on {n} spectra: PC1 explains {100 * evr[0]:.0f}% of the variance")
    summary += ". PCA is unsupervised: groups show where spectra differ, not why."
    return _section("PCA", COMPLETE if n >= pca_analysis.MIN_SPECTRA_WARN else PARTIAL, summary, res,
                    reason=None if n >= pca_analysis.MIN_SPECTRA_WARN else f"Only {n} spectra; structure may not be stable.")


def _benchmark_section(n_spectra, labels):
    have = len({l for l in labels if l})
    return _section("Model benchmark", INSUFFICIENT, "Insufficient data: benchmarking needs a labelled dataset.",
                    reason=(f"A benchmark trains and tests classifiers on labelled spectra split by independent specimen. This "
                            f"analysis has {n_spectra} spectrum/spectra and {have} distinct label(s); no train/test split is possible, "
                            "and metrics computed on it would be meaningless."),
                    requirements=["A labelled dataset with at least 2 classes and several independent specimens per class.",
                                  "Specimen identifiers, so repeats of one specimen never appear in both training and test data.",
                                  "The Research labs contain a protocol demonstration on simulated data; it does not describe your spectrum."],
                    data={"n_spectra": n_spectra, "distinct_labels": have})


def _translation_section():
    return _section("Spectral translation", INSUFFICIENT,
                    "Insufficient data: translation needs paired source and target spectra.",
                    reason=("Translation maps spectra from one instrument or condition to another. Evaluating it requires the same "
                            "specimens measured under both, plus a calibration standard measured on both. This input provides neither."),
                    requirements=["Paired spectra of the same specimens from the source and target instrument/condition.",
                                  "A calibration standard (e.g. polystyrene or silicon) measured on both setups."])


def _quality_section(a, origin_cat, sens):
    thr = a["quality_thresholds"]
    blocking = a["status"] == "inconclusive"
    sources = ["Instrument wavenumber calibration is not verified by RamanReach.",
               "Baseline correction (ALS) and smoothing can distort weak or broad bands.",
               "Fluorescence, cosmic rays and detector artefacts are not specifically detected."]
    if sens and sens["data"]["top1_changed_at"]:
        sources.append(f"The top-ranked reference changed under a simulated {sens['data']['top1_changed_at'][0]:+g} cm⁻¹ axis shift, "
                       "so calibration errors of that size would matter.")
    if origin_cat == "synthetic" or a["data_provenance"]["sample"].get("category") == "synthetic":
        sources.append("The input spectrum is synthetic, so results show software behaviour only.")
    verdict = "inconclusive" if blocking else "provisional checks passed"
    summary = ("Inconclusive: the evidence does not support a match claim." if blocking else
               "Provisional quality checks passed. This is not a validated identification.")
    snr = "undefined" if a["snr"] is None else f"{a['snr']:.1f}"
    summary += f" Estimated SNR: {snr} (provisional estimate)."
    return _section("Quality and reliability", COMPLETE, summary,
                    {"status": a["status"], "verdict": verdict, "conclusive": False, "snr": a["snr"], "warnings": a["quality_warnings"],
                     "thresholds": thr, "error_sources": sources, "limitations": a["limitations"],
                     "conclusive_note": "No result here is conclusive: thresholds are unvalidated and the reference library is synthetic."})


def _spectrum_section(a):
    return _section("Spectrum overview", COMPLETE, f"Raw and processed spectrum with {len(a['peaks'])} annotated peak(s).",
                    {"x": a["x"], "raw": a["raw"], "baseline": a["baseline"], "processed": a["processed"], "peaks": a["peaks"],
                     "parameters": a["parameters"], "units": {"x": "Raman shift (cm⁻¹)", "raw": "Intensity (as supplied)",
                                                             "processed": "Processed intensity (a.u.)"}})


def _summary_and_conclusion(a, sections, n_spectra):
    findings = [f"Analysed {a['sample_id']}: {len(a['x'])} points, {a['x'][0]:.0f}–{a['x'][-1]:.0f} cm⁻¹."]
    findings.append(sections["peaks"]["summary"])
    findings.append(sections["matching"]["summary"].split(" The reference library")[0])
    if sections["sensitivity"]["status"] == COMPLETE:
        findings.append(sections["sensitivity"]["summary"].split(" These are")[0])
    if sections["pca"]["status"] in (COMPLETE, PARTIAL):
        findings.append(sections["pca"]["summary"].split(". PCA is")[0] + ".")
    avail = [{"id": k, "title": s["title"], "status": s["status"]} for k, s in sections.items()]
    n_ok = sum(s["status"] in (COMPLETE, PARTIAL) for s in sections.values())
    n_ins = sum(s["status"] == INSUFFICIENT for s in sections.values())
    synth_refs = a["data_provenance"]["references_all_synthetic"]
    confidence = ("Low: the reference comparison is inconclusive. " if a["status"] == "inconclusive" else
                  "Limited: provisional checks passed, but the thresholds are unvalidated. ")
    if synth_refs:
        confidence += "References are idealised literature-band spectra; confirm against a measured reference. "
    confidence += "Wavenumber calibration was not verified."

    meaning = []
    if a["status"] == "inconclusive":
        meaning.append("The spectrum does not resemble any library reference clearly enough to name a candidate under the provisional rules.")
    else:
        m = a["matches"][0]
        meaning.append(f"The band shape of this spectrum is most similar to the '{m['name']}' reference among the {len(a['matches'])} references tested.")
    if a["peaks"]:
        top = sorted(a["peaks"], key=lambda p: -p["relative_height"])[:5]
        meaning.append("Distinct bands appear at " + ", ".join(f"{p['position']:.0f}" for p in top) + " cm⁻¹ (strongest first).")
    not_prove = ["A similarity score is not a probability that the sample is that material.",
                 "Peak region hints suggest bond types to consider; they do not establish composition.",
                 "Simulated sensitivity tests describe the software's behaviour, not your instrument's accuracy."]
    if synth_refs:
        not_prove.insert(0, "A match to an idealised literature-band reference is not a confirmed identification.")
    nxt = []
    if a.get("mixture"):
        nxt.append("If the sample may be a mixture, measure a few different spots on it separately.")
    snr = a["snr"]
    if snr is None or snr < quality.MIN_SNR:
        nxt.append("Measure again with a stronger signal: a longer exposure, more repeats, or better focus.")
    if a["matches"] and a["matches"][0]["coverage"] < quality.MIN_COVERAGE:
        nxt.append("Measure a wider range so it overlaps the reference spectra.")
    if any(p["near_boundary"] for p in a["peaks"]):
        nxt.append("Measure a slightly wider range: some peaks sit at the edge and may be cut off.")
    missing = sections["conditions"]["data"]["missing"]
    if missing:
        nxt.append("Write down how the spectrum was measured (" + ", ".join(METADATA_LABELS[k][0].lower() for k in missing[:3])
                   + ("…" if len(missing) > 3 else "") + ") so the result can be repeated.")
    nxt.append("Check the instrument's calibration with a silicon wafer in the same session: its peak should sit at 520.7 cm⁻¹.")
    if synth_refs:
        nxt.append("Confirm the match against a measured reference spectrum of the candidate material.")
    for k in ("pca", "benchmark", "translation"):
        if sections[k]["status"] == INSUFFICIENT and sections[k]["requirements"]:
            req = sections[k]["requirements"][0]
            nxt.append(f"To enable {sections[k]['title']}: {req[0].lower()}{req[1:]}")
    summary = {"analyzed": (f"One {'' if n_spectra == 1 else 'main '}spectrum ({a['sample_id']}, {a['source']})"
                            + (f" with {n_spectra - 1} additional spectrum/spectra" if n_spectra > 1 else "")
                            + f". {n_ok} analyses ran; {n_ins} need more data."),
               "findings": [f for f in findings if f], "confidence": confidence, "availability": avail,
               "status": a["status"]}
    return summary, {"meaning": meaning, "does_not_prove": not_prove, "next_steps": nxt}


NOT_PERFORMED_SHORT = {"pca": "requires three or more spectra", "benchmark": "requires a labelled training dataset",
                       "translation": "requires paired spectra from two instruments or conditions"}


def _brief(a, sections, conclusion, now):
    """The short research summary shown first: every value is copied from a computed section, nothing new is inferred."""
    ms, ok = a["matches"], a["status"] == "ok"
    top = ms[0] if ms else None
    lo, hi = a["x"][0], a["x"][-1]
    if ok and top:
        headline = f"The spectrum is most consistent with the {top['name']} reference (similarity {top['score']:.2f})."
    else:
        headline = "No reliable match to the reference library could be established."
    peaks = sorted(sections["peaks"]["data"]["peaks"], key=lambda p: -p["relative_height"])[:8]
    findings = []
    n_pk = len(a["peaks"])
    noisy = a["snr"] is None or a["snr"] < quality.MIN_SNR
    if peaks:
        findings.append(f"{n_pk} peak{'s' if n_pk != 1 else ''} detected; strongest at "
                        + ", ".join(f"{p['position']:.0f}" for p in peaks[:3]) + " cm⁻¹"
                        + ("; at this signal-to-noise many are likely noise." if noisy else "."))
    if top and ok:
        findings.append(f"Highest band-shape similarity: {top['name']} ({top['score']:.2f})"
                        + (f", ahead of {ms[1]['name']} ({ms[1]['score']:.2f})." if len(ms) > 1 else "."))
    elif top:
        findings.append(f"Closest reference: {top['name']} ({top['score']:.2f}), which does not meet the criteria for a match.")
    robustness = None
    sens = sections["sensitivity"]
    if sens["status"] == COMPLETE:
        d = sens["data"]
        robustness = (f"Top match changed under a simulated axis shift of {d['top1_changed_at'][0]:+g} cm⁻¹; stable within ±{d['stable_within_cm1']:g} cm⁻¹."
                      if d["top1_changed_at"] else f"Top match unchanged across simulated axis shifts of ±{d['tested_range_cm1']:g} cm⁻¹.")
        findings.append(robustness)
    limitations = []
    if not ok and a["quality_warnings"]:
        limitations.append(a["quality_warnings"][0])
    if a["data_provenance"]["references_all_synthetic"]:
        limitations.append("References are idealised literature-band spectra; confirm identifications against measured references.")
    if a["data_provenance"]["sample"].get("category") == "synthetic":
        limitations.append("Input is a bundled example spectrum generated from literature band positions.")
    limitations.append("Wavenumber calibration of the source instrument is not verified.")
    recs = [s for s in conclusion["next_steps"] if not s.startswith(("To enable", "Write down how"))][:3]
    return {
        "report_id": f"RR-{now:%Y%m%d-%H%M%S}",
        "verdict": "Provisional match" if ok else "Inconclusive",
        "headline": headline,
        "metrics": [
            {"label": "Peaks detected", "value": str(len(a["peaks"]))},
            {"label": "Best similarity", "value": f"{top['score']:.2f}" if top else "—", "note": "cosine, 0–1; not a probability"},
            {"label": "Signal-to-noise", "value": "undefined" if a["snr"] is None else f"{a['snr']:.0f}", "note": "provisional estimate"},
            {"label": "Spectral range", "value": f"{lo:.0f}–{hi:.0f} cm⁻¹"},
        ],
        "findings": findings[:3],
        "peaks": [{"position": p["position"], "relative_height": p["relative_height"],
                   "assignment": p["region_hints"][0] if p["region_hints"] else None,
                   "reference": p["near_reference_bands"][0] if p["near_reference_bands"] else None}
                  for p in sorted(peaks, key=lambda p: p["position"])],
        "references": [{"name": m["name"], "score": m["score"], "coverage": m["coverage"]} for m in ms[:3]],
        "match_claimed": ok,
        "robustness": robustness,
        "limitations": limitations[:3],
        "recommendations": recs,
        "not_performed": [{"title": sections[k]["title"], "reason": NOT_PERFORMED_SHORT[k]}
                          for k in NOT_PERFORMED_SHORT if sections[k]["status"] == INSUFFICIENT],
        "methods": _methods(a["parameters"]),
    }


def _methods(p):
    steps = []
    if p.get("baseline") == "als":
        steps.append(f"asymmetric least-squares baseline correction (λ={p['als_lambda']:g}, p={p['als_p']:g})")
    if p.get("smoothing") == "savgol":
        steps.append(f"Savitzky–Golay smoothing (window {p['savgol_window']}, order {p['savgol_poly']})")
    if p.get("normalization") != "none":
        steps.append(f"{p['normalization']} normalisation")
    pre = (", ".join(steps) if steps else "no preprocessing").capitalize()
    return (f"{pre}; peak detection at prominence ≥ {p['peak_prominence_frac']:g} of the intensity range; cosine similarity "
            f"against the reference library over the overlapping range; robustness tested by simulated axis shifts of the uploaded spectrum.")


# ---------------------------------------------------------------- orchestration

def _parse_extras(extras, excitation_nm):
    ok, failed = [], []
    for e in extras[:MAX_EXTRAS]:
        try:
            s = parse_any(e["raw"], e.get("filename") or e["name"], excitation_nm)
            ok.append({"name": e["name"], "label": e.get("label"), "x": s.x, "y": s.y})
            ok.extend({"name": f"{e['name']} / {c['name']}"[:80], "label": e.get("label"), "x": s.x, "y": c["y"]} for c in s.extra_y)
        except ValidationError as err:
            failed.append({"name": e["name"], "error": str(err)})
    for e in extras[MAX_EXTRAS:]:
        failed.append({"name": e["name"], "error": f"Only {MAX_EXTRAS} additional spectra are analysed."})
    return ok, failed


class Run:
    """Shared state of one analysis. Each stage function reads and fills it; run_linear() and the LangGraph workflow
    (app.agent.graph) both drive the same stage functions, so they produce identical reports and events."""

    def __init__(self, raw, sample_id="uploaded", source="uploaded file", excitation_nm=None, options=None, metadata=None,
                 extras=(), origin="unknown", provenance=None, truth=None, primary_label=None, filename=None):
        self.raw, self.sample_id, self.source, self.excitation_nm = raw, sample_id, source, excitation_nm
        self.opts = {"baseline": True, "als_lambda": 1e5, "als_p": 0.01, "smooth": True, "window": 11, "poly": 3,
                     "normalize": "vector", "prominence": 0.05, "despike": True}
        self.opts.update(options or {})
        self.metadata, self.extras = metadata, list(extras)
        self.origin = origin if origin in ORIGINS else "unknown"
        self.provenance, self.truth, self.primary_label, self.filename = provenance, truth, primary_label, filename
        self.sections, self.report = {}, None
        self.done = 0


def stage_validate(c: Run):
    try:
        c.spec = parse_any(c.raw, c.filename, c.excitation_nm)
        c.excitation_nm = c.excitation_nm or c.spec.meta.get("excitation_nm")  # a value stated in the file itself
        c.meta_in = dict(c.metadata or {})
        if c.excitation_nm:
            c.meta_in["excitation_nm"] = c.excitation_nm
        c.meta = ec.normalize_metadata(c.meta_in)
    except ValidationError as e:
        raise AnalysisFailed("validate", str(e))
    except (ValueError, TypeError) as e:
        raise AnalysisFailed("validate", f"Invalid experimental conditions: {e}")
    extras_ok, c.extras_failed = _parse_extras(c.extras, c.excitation_nm)
    # further spectra stored in the main file itself (extra columns, or one spectrum per row) count as additional spectra
    in_file = [{"name": e["name"], "label": None, "x": c.spec.x, "y": e["y"]} for e in c.spec.extra_y]
    room = max(0, MAX_EXTRAS - len(extras_ok))
    c.extras_ok = in_file[:room] + extras_ok
    if len(in_file) > room:
        c.extras_failed.append({"name": "columns in the main file", "error": f"Only {MAX_EXTRAS} additional spectra are analysed."})
    c.sections["validation"] = _validation_section(c.spec, c.extras_ok, c.extras_failed)
    return "done", f"{c.spec.x.size} points"


def stage_process(c: Run):
    c.cat, desc = ORIGINS[c.origin]
    c.prov = c.provenance or {"category": c.cat, "description": desc, "declared_origin": c.origin}
    try:
        c.a = pipeline.analyze(c.spec, c.sample_id, c.source, c.excitation_nm, c.opts, c.prov)
    except ValueError as e:
        raise AnalysisFailed("process", str(e))
    c.opts["library"] = c.a["data_provenance"]["library"]  # later stages compare against the same library
    c.sections["spectrum"] = _spectrum_section(c.a)
    c.sections["peaks"] = _peak_section(c.a)
    c.sections["matching"] = _matching_section(c.a)
    return "done", f"{len(c.a['peaks'])} peaks"


def stage_conditions(c: Run):
    dc = "synthetic_example" if c.prov.get("category") == "synthetic" else "measured"  # classes experiment_conditions knows
    cmp_res = cmp_err = None
    if c.extras_ok:
        try:
            base = {"label": c.a["sample_id"], "data_class": dc, "metadata": c.meta_in, "x": c.spec.x, "y": c.spec.y}
            exps = [{"label": e["name"][:60], "data_class": dc, "metadata": {}, "x": e["x"], "y": e["y"]} for e in c.extras_ok[:8]]
            cmp_res = ec.compare(base, exps, c.opts, c.truth)
            for e in cmp_res["experiments"]:
                for k in ("raw", "raw_x"):
                    e.pop(k, None)
            cmp_res["baseline"].pop("raw", None)
            cmp_res["baseline"].pop("raw_x", None)
            cmp_res["insights"] = ig.from_conditions(cmp_res)
            cmp_res["note"] = ("Additional spectra have no recorded conditions of their own, so differences cannot be attributed "
                               "to any parameter.")
        except ValueError as e:
            cmp_err = str(e)
    c.sections["conditions"] = _conditions_section(c.meta, c.spec, cmp_res, cmp_err)
    return "done", None


def stage_sensitivity(c: Run):
    """Wavenumber sensitivity on the user's own spectrum (simulated axis shifts). Optional: failure is reported."""
    try:
        s = ws.sweep(c.spec.x, c.spec.y, c.truth, "axis_shift", None, c.opts, None, 0, False, c.a["sample_id"])
        c.sections["sensitivity"] = _sensitivity_section(s)
        return "done", None
    except Exception as e:  # an optional analysis must not sink the report
        c.sections["sensitivity"] = _section("Wavenumber sensitivity", ERROR, "The sensitivity test could not be completed.", reason=str(e))
        return "error", str(e)


def stage_pca(c: Run):
    try:
        c.sections["pca"] = _pca_section({"name": c.a["sample_id"], "x": c.spec.x, "y": c.spec.y}, c.extras_ok, c.opts, c.primary_label)
        return ("skipped" if c.sections["pca"]["status"] == INSUFFICIENT else "done"), None
    except Exception as e:
        c.sections["pca"] = _section("PCA", ERROR, "PCA could not be completed.", reason=str(e))
        return "error", str(e)


def stage_models(c: Run):
    """Benchmark / translation availability: no computation is possible on a single upload."""
    c.n = 1 + len(c.extras_ok)
    c.sections["benchmark"] = _benchmark_section(c.n, [c.primary_label] + [e.get("label") for e in c.extras_ok])
    c.sections["translation"] = _translation_section()
    return "skipped", "insufficient data"


def stage_report(c: Run):
    sens = c.sections["sensitivity"] if c.sections["sensitivity"]["status"] == COMPLETE else None
    c.sections["quality"] = _quality_section(c.a, c.cat, sens)
    order = ["validation", "spectrum", "peaks", "matching", "conditions", "sensitivity", "pca", "benchmark", "translation", "quality"]
    sections = {k: c.sections[k] for k in order}
    summary, conclusion = _summary_and_conclusion(c.a, sections, c.n)
    analysis = {k: v for k, v in c.a.items() if k not in ("x", "raw", "baseline", "processed", "top_reference_curve")}
    now = datetime.now(timezone.utc)
    report = {
        "report_version": REPORT_VERSION, "software_version": pipeline.VERSION,
        "generated_at": now.isoformat(timespec="seconds"),
        "brief": _brief(c.a, sections, conclusion, now),
        "sample_id": c.a["sample_id"], "source": c.a["source"], "declared_origin": c.origin,
        "data_provenance": c.a["data_provenance"], "is_diagnostic": False,
        "inputs": {"n_spectra": c.n, "additional": [e["name"] for e in c.extras_ok], "options": c.opts, "metadata": c.meta_in,
                   "file_metadata": c.spec.meta, "truth_label": c.truth,
                   "truth_note": "Known only for bundled synthetic examples." if c.truth else None},
        "executive_summary": summary, "sections": sections, "conclusion": conclusion, "analysis": analysis,
        "evaluation": _evaluation_summary(c.a),
        "visual": visual.build(c.a, sections),
    }
    c.report = clean(report)
    return "done", None


def stage_explain(c: Run):
    """Plain-language summary. Without the LLM workflow this is the deterministic, rule-based version."""
    from . import explanation
    c.report["explanation"] = explanation.rule_based(c.report)
    return "done", "standard summary"


def _evaluation_summary(a):
    """Held-out performance of the measured library, cited only when the comparison actually used measured references."""
    if not a["data_provenance"].get("references_by_category", {}).get("measured"):
        return None
    ev = evaluation_real.load()
    if not ev:
        return None
    return {"headline": evaluation_real.headline(ev), "thresholds": ev["thresholds"], "date": ev["date"],
            "clean": ev["summary"]["clean"], "negative_control": ev["negative_control"],
            "n_materials": ev["n_materials"], "n_reference_spectra": ev["n_reference_spectra"]}


STAGE_FUNCS = {"validate": stage_validate, "process": stage_process, "conditions": stage_conditions,
               "sensitivity": stage_sensitivity, "pca": stage_pca, "models": stage_models, "report": stage_report,
               "explain": stage_explain}


def stage_event(c: Run, sid, status="running", detail=None):
    if status != "running":
        c.done += 1
    e = {"event": "stage", "stage": sid, "label": dict(STAGES)[sid], "status": status, "completed": c.done, "total": len(STAGES)}
    if status != "running":
        e["detail"] = detail
    return e


def run_linear(c: Run, funcs=None):
    funcs = {**STAGE_FUNCS, **(funcs or {})}
    for sid, _ in STAGES:
        yield stage_event(c, sid)
        try:
            status, detail = funcs[sid](c)
        except AnalysisFailed as e:
            yield {"event": "error", "stage": e.stage, "message": str(e)}
            return
        yield stage_event(c, sid, status, detail)
    yield {"event": "result", "report": c.report}


def run(raw: bytes, sample_id="uploaded", source="uploaded file", excitation_nm=None, options=None, metadata=None,
        extras=(), origin="unknown", provenance=None, truth=None, primary_label=None, filename=None, use_agent=None):
    """Yields {"event": "stage", ...} as each stage starts and ends, then {"event": "result", "report": ...}.
    A fatal problem (unreadable main file or invalid metadata) yields {"event": "error", ...} and stops.
    use_agent: None = use the LangGraph workflow when it is installed; False = the plain linear runner."""
    c = Run(raw, sample_id, source, excitation_nm, options, metadata, extras, origin, provenance, truth, primary_label, filename)
    if use_agent is not False:
        try:
            from ..agent import graph
        except ImportError:
            graph = None
        if graph is not None and graph.available():
            yield from graph.run(c)
            return
    yield from run_linear(c)


def build(*args, **kwargs) -> dict:
    """Non-streaming convenience: returns the report or raises AnalysisFailed."""
    for ev in run(*args, **kwargs):
        if ev["event"] == "error":
            raise AnalysisFailed(ev["stage"], ev["message"])
        if ev["event"] == "result":
            return ev["report"]
    raise AnalysisFailed("report", "Analysis ended without a report.")
