"""Heuristic quality gate.

All thresholds below are PROVISIONAL engineering heuristics. They have not been validated against labelled
measured data and must not be read as accuracy claims.
"""
import json
import pathlib

import numpy as np
from scipy.signal import savgol_filter

THRESHOLDS = {"min_snr": 5.0, "min_coverage": 0.7, "min_score": 0.6, "min_score_margin": 0.05, "min_sample_in_overlap": 0.6,
              "min_peak_fraction": 0.0}
THRESHOLD_STATUS = "provisional: unvalidated heuristics, not derived from measured reference data"
_CALIBRATED = pathlib.Path(__file__).resolve().parents[3] / "data" / "references_real" / "thresholds.json"
if _CALIBRATED.exists():  # written by scripts/evaluate_library.py from the held-out evaluation
    _c = json.loads(_CALIBRATED.read_text(encoding="utf-8"))
    THRESHOLDS.update({k: float(_c[k]) for k in ("min_score", "min_score_margin", "min_peak_fraction") if k in _c})
    THRESHOLD_STATUS = (f"min_score, min_score_margin and min_peak_fraction calibrated on {_c.get('n_calibration_queries', '?')} held-out measured "
                        f"spectra ({_c.get('date', '?')}) for a false-match rate <= {_c.get('target_false_match_rate', 0.05):.0%}; "
                        "SNR and coverage limits remain provisional heuristics")
MIN_SNR = THRESHOLDS["min_snr"]
MIN_COVERAGE = THRESHOLDS["min_coverage"]
MIN_SCORE = THRESHOLDS["min_score"]
MIN_MARGIN = THRESHOLDS["min_score_margin"]
MIN_SAMPLE_IN_OVERLAP = THRESHOLDS["min_sample_in_overlap"]
MIN_PEAK_FRACTION = THRESHOLDS["min_peak_fraction"]
_SIGNAL_WINDOW = 11  # fixed internal smoothing for the signal term only; independent of user settings


def estimate_snr(baseline_removed):
    """Provisional SNR estimate that does not depend on the user's smoothing choice.

    noise  = robust sigma from the first differences (1.4826 * MAD / sqrt(2)); this over-estimates noise on
             very smooth, densely sampled data, so the SNR is conservative there.
    signal = height of the strongest feature above the median of a fixed-window smoothed copy.
    Returns None when noise is zero or non-finite (SNR undefined) - never an artificial large number.
    """
    y = np.asarray(baseline_removed, float)
    if y.size < 3:
        return None
    d = np.diff(y)
    sigma = 1.4826 * np.median(np.abs(d - np.median(d))) / np.sqrt(2)
    # Noise below a tiny fraction of the signal range is floating-point residue, not a measurement of noise.
    if not np.isfinite(sigma) or sigma <= 1e-9 * max(float(np.ptp(y)), 1e-300):
        return None
    sm = savgol_filter(y, _SIGNAL_WINDOW, 3) if y.size >= _SIGNAL_WINDOW else y
    signal = float(np.max(sm) - np.median(sm))
    return signal / sigma


def saturation(raw_y, min_run=3):
    """Detector saturation shows as a flat top: several consecutive points at exactly the maximum value.
    Returns a warning string, or None."""
    y = np.asarray(raw_y, float)
    at_max = y == np.max(y)
    run = best = 0
    for v in at_max:
        run = run + 1 if v else 0
        best = max(best, run)
    if best >= min_run:
        return (f"The strongest band is flat-topped ({best} consecutive points at the maximum value): the detector was "
                "probably saturated, so band shapes and relative intensities near it are unreliable.")
    return None


def assess(snr, matches, info, mixture=None):
    """Returns (status, reasons). Blocking reasons make the result 'inconclusive'; `info` are non-blocking notes."""
    blocking = []
    if snr is None:
        blocking.append("Signal-to-noise ratio could not be estimated (noise estimate is zero or undefined).")
    elif snr < MIN_SNR:
        blocking.append(f"Low signal-to-noise ratio ({snr:.1f} < provisional threshold {MIN_SNR:g}).")
    if not matches or matches[0]["coverage"] < MIN_COVERAGE:
        blocking.append(f"Insufficient overlap with reference range (< {int(MIN_COVERAGE * 100)}% coverage, provisional).")
    else:
        if matches[0].get("sample_signal_in_overlap", 1.0) < MIN_SAMPLE_IN_OVERLAP:
            blocking.append(f"Only {matches[0]['sample_signal_in_overlap'] * 100:.0f}% of the sample's band intensity lies inside the "
                            f"range of the closest reference ({matches[0]['name']}), so most bands were not compared.")
        if matches[0]["score"] < MIN_SCORE:
            blocking.append(f"Highest similarity ({matches[0]['score']:.2f}) is below the provisional {MIN_SCORE:g} threshold.")
        pa = matches[0].get("peak_agreement") or {}
        n_ref = pa.get("reference_peaks_in_overlap") or 0
        if MIN_PEAK_FRACTION > 0 and n_ref and len(pa.get("matched", [])) / n_ref < MIN_PEAK_FRACTION:
            blocking.append(f"Only a few of the closest reference's bands were found in the sample ({len(pa['matched'])} of {n_ref}; "
                            f"at least {MIN_PEAK_FRACTION:.0%} are required).")
        if mixture:
            blocking.append(f"The spectrum is explained better by a mixture of {mixture['names'][0]} and {mixture['names'][1]} "
                            f"(fit {mixture['fit_score']:.2f} vs {mixture['single_score']:.2f} for the best single reference), so "
                            "naming one material would be misleading.")
        if len(matches) > 1 and matches[0]["score"] - matches[1]["score"] < MIN_MARGIN:
            blocking.append("Top candidates have near-identical scores (provisional margin check).")
    return ("inconclusive" if blocking else "ok"), blocking + list(info)
