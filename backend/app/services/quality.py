"""Heuristic quality gate.

All thresholds below are PROVISIONAL engineering heuristics. They have not been validated against labelled
measured data and must not be read as accuracy claims.
"""
import numpy as np
from scipy.signal import savgol_filter

THRESHOLDS = {"min_snr": 5.0, "min_coverage": 0.7, "min_score": 0.6, "min_score_margin": 0.05}
THRESHOLD_STATUS = "provisional: unvalidated heuristics, not derived from measured reference data"
MIN_SNR = THRESHOLDS["min_snr"]
MIN_COVERAGE = THRESHOLDS["min_coverage"]
MIN_SCORE = THRESHOLDS["min_score"]
MIN_MARGIN = THRESHOLDS["min_score_margin"]
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


def assess(snr, matches, info):
    """Returns (status, reasons). Blocking reasons make the result 'inconclusive'; `info` are non-blocking notes."""
    blocking = []
    if snr is None:
        blocking.append("Signal-to-noise ratio could not be estimated (noise estimate is zero or undefined).")
    elif snr < MIN_SNR:
        blocking.append(f"Low signal-to-noise ratio ({snr:.1f} < provisional threshold {MIN_SNR:g}).")
    if not matches or matches[0]["coverage"] < MIN_COVERAGE:
        blocking.append(f"Insufficient overlap with reference range (< {int(MIN_COVERAGE * 100)}% coverage, provisional).")
    else:
        if matches[0]["score"] < MIN_SCORE:
            blocking.append(f"Highest similarity ({matches[0]['score']:.2f}) is below the provisional {MIN_SCORE:g} threshold.")
        if len(matches) > 1 and matches[0]["score"] - matches[1]["score"] < MIN_MARGIN:
            blocking.append("Top candidates have near-identical scores (provisional margin check).")
    return ("inconclusive" if blocking else "ok"), blocking + list(info)
