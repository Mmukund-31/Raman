"""End-to-end analysis orchestration, independent of HTTP."""
import csv
import functools
import json
import pathlib
from datetime import datetime, timezone

import numpy as np

from . import matching, peak_detection, preprocessing, quality
from .validation import Spectrum

VERSION = "0.2.0"
DATA_DIR = pathlib.Path(__file__).resolve().parents[3] / "data"
SIMILARITY_NOTE = ("Scores are cosine similarities of band shape over the overlapping range under the chosen "
                   "preprocessing. They are not probabilities of identification.")
LIMITATIONS = [
    "Experimental research prototype. Not a diagnostic or clinical tool, and not a reliable means of identifying medicines.",
    SIMILARITY_NOTE,
    "Quality thresholds are provisional heuristics that have not been validated on measured data.",
    "The bundled reference library is synthetic (idealised bands), so results demonstrate the workflow only.",
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


@functools.lru_cache(maxsize=1)
def _load_references_cached() -> tuple:
    refs = []
    for m in load_manifest("references"):
        x, y = read_xy(DATA_DIR / "references" / m["file"])
        refs.append({"id": m["reference_id"], "name": m["name"], "x": x, "y": y, "category": m["category"],
                     "source": m["source"]})
    return tuple(refs)


def load_references() -> list[dict]:
    """Read once per process; callers must not mutate the returned arrays."""
    return list(_load_references_cached())


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
            provenance=None) -> dict:
    o = {"baseline": True, "als_lambda": 1e5, "als_p": 0.01, "smooth": True, "window": 11, "poly": 3,
         "normalize": "vector", "prominence": 0.05}
    o.update(options or {})
    provenance = provenance or USER_PROVENANCE
    x, y = spec.x, spec.y
    processed, base, params = preprocessing.preprocess(
        y, o["baseline"], o["als_lambda"], o["als_p"], o["smooth"], o["window"], o["poly"], o["normalize"])
    snr = quality.estimate_snr(y - base)  # independent of smoothing/normalization choices
    peaks = peak_detection.detect_peaks(x, processed, o["prominence"])
    sample_pos = [p["position"] for p in peaks]
    refs, ref_peaks = [], {}
    for r in load_references():
        ry, _, _ = preprocessing.preprocess(r["y"], o["baseline"], o["als_lambda"], o["als_p"], o["smooth"],
                                            o["window"], o["poly"], "none")
        refs.append({**r, "y": ry})
        ref_peaks[r["id"]] = [p["position"] for p in peak_detection.detect_peaks(r["x"], ry, o["prominence"])]
    matches = matching.compare(x, processed, refs)
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
    if not excitation_nm and not spec.converted:
        info.append("Excitation wavelength not provided (metadata only; Raman-shift input was analysed as given).")
    if provenance["category"] == "synthetic":
        info.append("Input spectrum is SYNTHETIC test data, not a physical measurement.")
    synthetic_refs = any(r["category"] == "synthetic" for r in refs)
    if synthetic_refs:
        info.append("Reference library is SYNTHETIC (idealised bands). Similarity to it cannot support identification of a real material.")
    status, reasons = quality.assess(snr, matches, info)
    return {
        "sample_id": sample_id, "source": source, "status": status, "quality_warnings": reasons,
        "snr": None if snr is None else round(snr, 2),
        "metadata": _metadata(spec, excitation_nm), "excitation_nm": excitation_nm,
        "data_provenance": {
            "sample": provenance,
            "references": [{"reference_id": r["id"], "category": r["category"], "source": r["source"]} for r in refs],
            "references_all_synthetic": all(r["category"] == "synthetic" for r in refs),
        },
        "quality_thresholds": {**quality.THRESHOLDS, "status": quality.THRESHOLD_STATUS},
        "x": x.tolist(), "raw": y.tolist(), "baseline": base.tolist(), "processed": processed.tolist(),
        "peaks": peaks, "matches": matches, "top_matches": [] if status == "inconclusive" else matches[:3],
        "similarity_note": SIMILARITY_NOTE,
        "parameters": {**params, "peak_prominence_frac": o["prominence"]},
        "limitations": LIMITATIONS, "software_version": VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "is_diagnostic": False,
    }


def identify(x, y, options=None, truth=None) -> dict:
    """Compact identification summary from the SAME pipeline as analyze(); used by sweeps and experiments."""
    res = analyze(Spectrum(np.asarray(x, float), np.asarray(y, float)), "sweep", "internal", None, options)
    ms = res["matches"]
    out = {"status": res["status"], "snr": res["snr"], "top1": ms[0]["reference_id"], "top1_score": ms[0]["score"],
           "margin": ms[0]["score"] - ms[1]["score"] if len(ms) > 1 else None,
           "scores": {m["reference_id"]: m["score"] for m in ms}, "peaks": res["peaks"],
           "processed": res["processed"], "x": res["x"], "reasons": res["quality_warnings"]}
    if truth is not None:
        out["truth_score"] = out["scores"].get(truth)
        out["correct"] = res["status"] == "ok" and out["top1"] == truth
    return out
