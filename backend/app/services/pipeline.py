"""End-to-end analysis orchestration, independent of HTTP."""
import csv
import json
import pathlib
from datetime import datetime, timezone

import numpy as np

from . import matching, peak_detection, preprocessing, quality
from .validation import Spectrum

VERSION = "0.1.0"
DATA_DIR = pathlib.Path(__file__).resolve().parents[3] / "data"
LIMITATIONS = [
    "Experimental research prototype. Not a diagnostic or clinical tool.",
    "Similarity scores are cosine similarities under the chosen preprocessing, not probabilities of identification.",
    "The bundled reference library is small and synthetic (idealised bands), so results demonstrate the workflow only.",
    "Results depend on instrument resolution, calibration and sample conditions that this software cannot verify.",
]


def load_manifest(kind: str) -> list[dict]:
    return json.loads((DATA_DIR / kind / "manifest.json").read_text())


def read_xy(path: pathlib.Path):
    with open(path, newline="") as f:
        rows = list(csv.reader(f))[1:]
    a = np.array(rows, float)
    return a[:, 0], a[:, 1]


def load_references() -> list[dict]:
    refs = []
    for m in load_manifest("references"):
        x, y = read_xy(DATA_DIR / "references" / m["file"])
        refs.append({"id": m["reference_id"], "name": m["name"], "x": x, "y": y, "category": m["category"]})
    return refs


def analyze(spec: Spectrum, sample_id="sample", source="uploaded", excitation_nm=None, options=None) -> dict:
    o = {"baseline": True, "als_lambda": 1e5, "als_p": 0.01, "smooth": True, "window": 11, "poly": 3,
         "normalize": "vector", "prominence": 0.05}
    o.update(options or {})
    x, y = spec.x, spec.y
    processed, base, params = preprocessing.preprocess(
        y, o["baseline"], o["als_lambda"], o["als_p"], o["smooth"], o["window"], o["poly"], o["normalize"])
    # SNR uses an un-normalized version of the same pipeline
    unnorm, _, _ = preprocessing.preprocess(y, o["baseline"], o["als_lambda"], o["als_p"], o["smooth"],
                                            o["window"], o["poly"], "none")
    snr = quality.estimate_snr(unnorm, y - base)
    peaks = peak_detection.detect_peaks(x, processed, o["prominence"])
    refs = []
    for r in load_references():
        ry, _, _ = preprocessing.preprocess(r["y"], o["baseline"], o["als_lambda"], o["als_p"], o["smooth"],
                                            o["window"], o["poly"], "none")
        refs.append({**r, "y": ry})
    matches = matching.compare(x, processed, refs)
    status, reasons = quality.assess(snr, matches, bool(excitation_nm), spec.warnings)
    if status == "inconclusive":
        top = []
    else:
        top = matches[:3]
    return {
        "sample_id": sample_id, "source": source, "status": status, "quality_warnings": reasons,
        "snr": round(snr, 2), "excitation_nm": excitation_nm,
        "x": x.tolist(), "raw": y.tolist(), "baseline": base.tolist(), "processed": processed.tolist(),
        "peaks": peaks, "matches": matches, "top_matches": top,
        "parameters": {**params, "peak_prominence_frac": o["prominence"]},
        "limitations": LIMITATIONS, "software_version": VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "is_diagnostic": False,
    }
