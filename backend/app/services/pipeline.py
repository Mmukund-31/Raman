"""End-to-end analysis orchestration, independent of HTTP."""
import csv
import functools
import json
import pathlib
from datetime import datetime, timezone

import numpy as np

from . import matching, peak_detection, preprocessing, quality
from .validation import Spectrum

VERSION = "0.3.0"
DATA_DIR = pathlib.Path(__file__).resolve().parents[3] / "data"
SIMILARITY_NOTE = ("Scores are cosine similarities of band shape over the overlapping range under the chosen "
                   "preprocessing. They are not probabilities of identification.")
LIMITATIONS = [
    "Experimental research prototype. Not a diagnostic or clinical tool, and not a reliable means of identifying medicines.",
    SIMILARITY_NOTE,
    "Quality thresholds are provisional heuristics that have not been validated on measured data.",
    "Reference spectra come from public databases (RRUFF, ROD) and a synthetic demo set; a library can only recognise "
    "materials it contains, and synthetic references cannot identify a real material.",
    "Instrument calibration of the x-axis is not verified by this software; excitation wavelength is user-declared metadata.",
    "Results depend on instrument resolution, calibration and sample conditions that this software cannot assess.",
]
USER_PROVENANCE = {"category": "user_supplied", "description": "Uploaded by the user; origin and calibration not verified by RamanReach."}


def load_manifest(kind: str) -> list[dict]:
    return json.loads((DATA_DIR / kind / "manifest.json").read_text())


def read_xy(path: pathlib.Path):
    with open(path, newline="") as f:
        rows = list(csv.reader(f))[1:]
    a = np.array(rows, float)
    return a[:, 0], a[:, 1]


# Named reference libraries -> data folders. 'synthetic_demo' is the original idealised set the research labs are built
# on; 'measured' is the curated set of real spectra (data/references_real, built by scripts/curate_library.py).
LIBRARIES = {"synthetic_demo": ("references",), "measured": ("references_real",), "all": ("references", "references_real")}
DEFAULT_LIBRARY = "synthetic_demo"


@functools.lru_cache(maxsize=4)
def _load_references_cached(library: str = DEFAULT_LIBRARY) -> tuple:
    if library not in LIBRARIES:
        raise ValueError(f"Unknown reference library '{library}'. Choose one of: {', '.join(LIBRARIES)}.")
    refs = []
    for folder in LIBRARIES[library]:
        if not (DATA_DIR / folder / "manifest.json").exists():
            continue  # the measured library is optional until it has been curated
        for m in load_manifest(folder):
            x, y = read_xy(DATA_DIR / folder / m["file"])
            refs.append({"id": m["reference_id"], "name": m["name"], "x": x, "y": y, "category": m["category"],
                         "source": m["source"], "material": m.get("material", m["reference_id"]),
                         **{k: m[k] for k in ("source_id", "citation", "excitation_nm") if m.get(k) is not None}})
    return tuple(refs)


def load_references(library: str = DEFAULT_LIBRARY) -> list[dict]:
    """Read once per process; callers must not mutate the returned arrays."""
    return list(_load_references_cached(library))


def library_for(options: dict, provenance: dict) -> str:
    """'auto' compares bundled synthetic examples with the synthetic set they were generated from, everything else
    with every available library."""
    lib = (options or {}).get("library") or "auto"
    if lib == "auto":
        return "synthetic_demo" if provenance.get("category") == "synthetic" else "all"
    return lib


@functools.lru_cache(maxsize=16)
def _prepared_references(library, baseline, lam, p, smooth, window, poly, prominence) -> tuple:
    """References preprocessed exactly like the sample (minus normalisation) plus their peak positions; cached because
    sweeps and evaluations call analyze() many times with the same settings."""
    out = []
    for r in _load_references_cached(library):
        ry, _, _ = preprocessing.preprocess(r["y"], baseline, lam, p, smooth, window, poly, "none")
        pk = tuple(q["position"] for q in peak_detection.detect_peaks(r["x"], ry, prominence))
        out.append(({**r, "y": ry}, pk))
    return tuple(out)


def _metadata(spec: Spectrum, excitation_nm):
    """Coordinate conversion, excitation metadata and calibration status are reported separately."""
    return {
        "coordinate_input": spec.coordinate_input,
        "wavelength_converted_to_raman_shift": spec.converted,
        "excitation_nm": excitation_nm,
        "excitation_source": "user-declared" if excitation_nm else "not provided",
        "calibration_status": "not_verified",
        "calibration_note": "RamanReach cannot verify wavelength/Raman-shift calibration of the source instrument.",
    }


def analyze(spec: Spectrum, sample_id="sample", source="uploaded", excitation_nm=None, options=None,
            provenance=None, exclude_refs=frozenset()) -> dict:
    """exclude_refs: reference ids left out of the comparison (held-out evaluation uses it to remove the query's own
    specimen, or its whole material for negative controls)."""
    o = {"baseline": True, "als_lambda": 1e5, "als_p": 0.01, "smooth": True, "window": 11, "poly": 3,
         "normalize": "vector", "prominence": 0.05, "despike": True}
    o.update(options or {})
    provenance = provenance or USER_PROVENANCE
    x, y = spec.x, spec.y
    y_in, n_spikes = preprocessing.despike(y) if o["despike"] else (y, 0)  # raw y is kept unmodified for display
    processed, base, params = preprocessing.preprocess(
        y_in, o["baseline"], o["als_lambda"], o["als_p"], o["smooth"], o["window"], o["poly"], o["normalize"])
    params["despike"] = "median" if o["despike"] else "none"
    params["spikes_removed"] = n_spikes
    snr = quality.estimate_snr(y_in - base)  # independent of smoothing/normalization choices
    peaks = peak_detection.detect_peaks(x, processed, o["prominence"])
    sample_pos = [p["position"] for p in peaks]
    library = library_for(o, provenance)
    prepared = _prepared_references(library, o["baseline"], o["als_lambda"], o["als_p"], o["smooth"], o["window"],
                                    o["poly"], o["prominence"])
    prepared = [(r, pk) for r, pk in prepared if r["id"] not in exclude_refs]
    refs = [r for r, _ in prepared]
    ref_peaks = {r["id"]: list(pk) for r, pk in prepared}
    if not refs:
        raise ValueError(f"The '{library}' reference library is empty.")
    matches = matching.best_per_material(matching.compare(x, processed, refs))
    for m in matches:
        pa = matching.peak_agreement(sample_pos, ref_peaks[m["reference_id"]], m["overlap"])
        m["peak_agreement"] = pa
        if m["overlap"] is None:
            m["explanation"] = "No overlap between the sample and this reference."
        else:
            m["explanation"] = (
                f"Cosine similarity {m['score']:.2f} over {m['overlap'][0]:.0f}-{m['overlap'][1]:.0f} cm-1 "
                f"({m['coverage'] * 100:.0f}% of the reference range). {len(pa['matched'])} of "
                f"{pa['reference_peaks_in_overlap']} reference peaks in that range have a detected sample peak within "
                f"±{pa['tolerance_cm1']:g} cm-1. This describes band-shape agreement, not the probability of identification.")

    info = list(spec.warnings)
    if n_spikes:
        info.append(f"{n_spikes} point(s) looked like cosmic-ray spikes and were interpolated over before processing.")
    sat = quality.saturation(y)
    if sat:
        info.append(sat)
    if not excitation_nm and not spec.converted:
        info.append("Excitation wavelength not provided (metadata only; Raman-shift input was analysed as given).")
    if provenance["category"] == "synthetic":
        info.append("Input spectrum is SYNTHETIC test data, not a physical measurement.")
    if all(r["category"] == "synthetic" for r in refs):
        info.append("Reference library is SYNTHETIC (idealised bands). Similarity to it cannot support identification of a real material.")
    elif matches and matches[0].get("category") == "synthetic":
        info.append(f"The closest reference ({matches[0]['name']}) is SYNTHETIC (idealised bands), so it cannot support "
                    "identification of a real material.")
    mixture = matching.mixture_check(x, processed, {r["id"]: r for r in refs}, matches[:5])
    status, reasons = quality.assess(snr, matches, info, mixture)
    return {
        "sample_id": sample_id, "source": source, "status": status, "quality_warnings": reasons,
        "snr": None if snr is None else round(snr, 2),
        "metadata": _metadata(spec, excitation_nm), "excitation_nm": excitation_nm,
        "data_provenance": {
            "sample": provenance,
            "library": library,
            "n_reference_spectra": len(refs), "n_materials": len(matches),
            "references_by_category": {c: sum(r["category"] == c for r in refs) for c in sorted({r["category"] for r in refs})},
            "references": [{"reference_id": r["id"], "category": r["category"], "source": r["source"]} for r in refs][:200],
            "references_all_synthetic": all(r["category"] == "synthetic" for r in refs),
            "top_match_synthetic": bool(matches) and matches[0].get("category") == "synthetic",
        },
        "quality_thresholds": {**quality.THRESHOLDS, "status": quality.THRESHOLD_STATUS},
        "x": x.tolist(), "raw": y.tolist(), "baseline": base.tolist(), "processed": processed.tolist(),
        "peaks": peaks, "matches": matches, "top_matches": [] if status == "inconclusive" else matches[:3],
        "mixture": mixture,
        "top_reference_curve": _curve(refs, matches[0]) if matches else None,
        "similarity_note": SIMILARITY_NOTE,
        "parameters": {**params, "peak_prominence_frac": o["prominence"]},
        "limitations": LIMITATIONS, "software_version": VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "is_diagnostic": False,
    }


def _curve(refs, m):
    """The best match's preprocessed reference spectrum (for drawing it beside the sample), at most ~1000 points."""
    r = next((r for r in refs if r["id"] == m["reference_id"]), None)
    if r is None:
        return None
    step = max(1, r["x"].size // 1000)
    return {"reference_id": r["id"], "name": r["name"], "x": r["x"][::step].tolist(), "y": r["y"][::step].tolist()}


def identify(x, y, options=None, truth=None) -> dict:
    """Compact identification summary from the SAME pipeline as analyze(); used by sweeps and experiments."""
    opts = {"library": DEFAULT_LIBRARY, **(options or {})}  # the labs simulate the synthetic materials unless told otherwise
    res = analyze(Spectrum(np.asarray(x, float), np.asarray(y, float)), "sweep", "internal", None, opts)
    ms = res["matches"]
    out = {"status": res["status"], "snr": res["snr"], "top1": ms[0]["material"], "top1_score": ms[0]["score"],
           "margin": ms[0]["score"] - ms[1]["score"] if len(ms) > 1 else None,
           "scores": {m["material"]: m["score"] for m in ms}, "peaks": res["peaks"],
           "processed": res["processed"], "x": res["x"], "reasons": res["quality_warnings"]}
    if truth is not None:
        out["truth_score"] = out["scores"].get(truth)
        out["correct"] = res["status"] == "ok" and out["top1"] == truth
    return out
