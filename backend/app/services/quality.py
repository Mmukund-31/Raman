import numpy as np

MIN_COVERAGE = 0.7
MIN_SCORE = 0.6
MIN_MARGIN = 0.05
MIN_SNR = 5.0


def estimate_snr(smoothed, baseline_removed):
    """Signal = peak-to-peak of smoothed spectrum; noise = std of (baseline-removed minus smoothed)."""
    noise = float(np.std(baseline_removed - smoothed))
    sig = float(np.ptp(smoothed))
    return sig / noise if noise > 0 else 1e9


def assess(snr, matches, has_excitation, warnings):
    """Returns (status, reasons). Missing excitation metadata is a warning only; the rest block a match claim."""
    info = list(warnings)
    blocking = []
    if snr < MIN_SNR:
        blocking.append(f"Low signal-to-noise ratio ({snr:.1f} < {MIN_SNR:g}).")
    if not matches or matches[0]["coverage"] < MIN_COVERAGE:
        blocking.append(f"Insufficient overlap with reference range (< {int(MIN_COVERAGE * 100)}% coverage).")
    else:
        if matches[0]["score"] < MIN_SCORE:
            blocking.append(f"Best similarity ({matches[0]['score']:.2f}) is below the {MIN_SCORE:g} threshold.")
        if len(matches) > 1 and matches[0]["score"] - matches[1]["score"] < MIN_MARGIN:
            blocking.append("Top candidates have near-identical scores.")
    if not has_excitation:
        info.append("Excitation wavelength metadata missing; calibration cannot be verified.")
    return ("inconclusive" if blocking else "ok"), blocking + info
