"""Controlled perturbations: an EVALUATION tool, never a substitute for measurements.

Every function returns (x, y, record). The record states what was done and what class of effect it represents:
- axis_calibration: the spectral coordinate is wrong relative to the signal (x changes, y does not)
- physical: the signal itself changes on a fixed axis (y changes)
- instrumental / processing: response, noise, range
All outputs are SIMULATED. From a spectrum alone, a global axis-calibration shift and a physical global peak shift are
indistinguishable in the reported coordinates; they differ in cause and can only be separated with metadata or a
calibration standard.
"""
import numpy as np
from scipy.ndimage import gaussian_filter1d

KINDS = {
    "axis_shift": {"class": "axis_calibration", "label": "Global axis shift (calibration error)", "params": ["delta_cm1"]},
    "axis_warp": {"class": "axis_calibration", "label": "Nonlinear axis warp (calibration error)", "params": ["amplitude_cm1"]},
    "signal_shift": {"class": "physical", "label": "Global peak shift of the signal (physical change)", "params": ["delta_cm1"]},
    "broadening": {"class": "physical", "label": "Peak broadening", "params": ["sigma_cm1"]},
    "baseline_distortion": {"class": "instrumental", "label": "Baseline distortion (fluorescence-like)", "params": ["amplitude_frac"]},
    "intensity_scale": {"class": "instrumental", "label": "Intensity scaling", "params": ["factor"]},
    "noise": {"class": "instrumental", "label": "Additive Gaussian noise", "params": ["sigma_frac"]},
    "laser_power": {"class": "instrumental", "label": "Laser-power change (gain + shot noise + optional saturation)",
                    "params": ["factor"]},
    "temperature": {"class": "physical", "label": "Temperature (USER-SPECIFIED coefficients, not material data)",
                    "params": ["delta_T_K", "shift_coeff_cm1_per_K", "broadening_coeff_cm1_per_K"]},
    "truncation": {"class": "processing", "label": "Spectral-range truncation", "params": ["lo", "hi"]},
}


def _record(kind, params, seed=None):
    return {"kind": kind, "class": KINDS[kind]["class"], "label": KINDS[kind]["label"], "params": params,
            "seed": seed, "simulated": True}


def _step(x):
    return float(np.median(np.diff(x)))


def axis_shift(x, y, delta_cm1: float):
    return np.asarray(x, float) + delta_cm1, np.asarray(y, float).copy(), _record("axis_shift", {"delta_cm1": delta_cm1})


def axis_warp(x, y, amplitude_cm1: float):
    """Quadratic warp: 0 at the range centre, +amplitude at both ends (a simple nonlinear calibration error)."""
    x = np.asarray(x, float)
    mid, half = (x[0] + x[-1]) / 2, (x[-1] - x[0]) / 2
    return x + amplitude_cm1 * ((x - mid) / half) ** 2, np.asarray(y, float).copy(), \
        _record("axis_warp", {"amplitude_cm1": amplitude_cm1})


def signal_shift(x, y, delta_cm1: float):
    """Peaks move by +delta on a fixed axis. Edge samples are held constant (an artefact; flagged in the record)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    rec = _record("signal_shift", {"delta_cm1": delta_cm1})
    rec["note"] = "Edge values are held constant where the shifted signal leaves the measured range."
    return x.copy(), np.interp(x - delta_cm1, x, y), rec


def broadening(x, y, sigma_cm1: float):
    x, y = np.asarray(x, float), np.asarray(y, float)
    if sigma_cm1 < 0:
        raise ValueError("sigma_cm1 must be >= 0.")
    out = gaussian_filter1d(y, sigma_cm1 / _step(x), mode="nearest") if sigma_cm1 > 0 else y.copy()
    return x.copy(), out, _record("broadening", {"sigma_cm1": sigma_cm1})


def baseline_distortion(x, y, amplitude_frac: float):
    """Adds a smooth decaying, fluorescence-like background of height amplitude_frac * (peak-to-peak of y)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    t = (x - x[0]) / (x[-1] - x[0])
    return x.copy(), y + amplitude_frac * np.ptp(y) * (1 - t) ** 2, \
        _record("baseline_distortion", {"amplitude_frac": amplitude_frac})


def intensity_scale(x, y, factor: float):
    if factor <= 0:
        raise ValueError("factor must be > 0.")
    return np.asarray(x, float).copy(), np.asarray(y, float) * factor, _record("intensity_scale", {"factor": factor})


def noise(x, y, sigma_frac: float, seed: int = 0):
    """Gaussian noise with sigma = sigma_frac * peak-to-peak of y."""
    y = np.asarray(y, float)
    rng = np.random.default_rng(seed)
    return np.asarray(x, float).copy(), y + rng.normal(0, sigma_frac * np.ptp(y), y.size), \
        _record("noise", {"sigma_frac": sigma_frac}, seed)


def laser_power(x, y, factor: float, seed: int = 0, saturation_counts: float | None = None, shot_k: float = 1.0):
    """Illustrative power change. Signal gain = factor; shot noise sigma = shot_k * sqrt(gained non-negative signal);
    optional hard saturation. Real response also involves heating, fluorescence and detector behaviour, which are
    NOT modelled; the factor is a ratio of powers only when geometry (spot, focus) is unchanged."""
    if factor <= 0:
        raise ValueError("factor must be > 0.")
    y = np.asarray(y, float)
    rng = np.random.default_rng(seed)
    g = y * factor
    out = g + rng.normal(0, shot_k * np.sqrt(np.clip(g, 0, None)))
    if saturation_counts is not None:
        out = np.minimum(out, saturation_counts)
    return np.asarray(x, float).copy(), out, _record(
        "laser_power", {"factor": factor, "saturation_counts": saturation_counts, "shot_k": shot_k}, seed)


def temperature(x, y, delta_T_K: float, shift_coeff_cm1_per_K: float, broadening_coeff_cm1_per_K: float = 0.0):
    """Applies a USER-SPECIFIED linear peak shift and extra Gaussian broadening per kelvin. The coefficients are
    assumptions supplied by the caller; real temperature dependence is material- and mode-specific."""
    x2, y2, _ = signal_shift(x, y, shift_coeff_cm1_per_K * delta_T_K)
    sigma = abs(broadening_coeff_cm1_per_K * delta_T_K)
    if sigma > 0:
        _, y2, _ = broadening(x2, y2, sigma)
    rec = _record("temperature", {"delta_T_K": delta_T_K, "shift_coeff_cm1_per_K": shift_coeff_cm1_per_K,
                                  "broadening_coeff_cm1_per_K": broadening_coeff_cm1_per_K})
    rec["note"] = "Coefficients are user-specified assumptions, not measured material properties."
    return x2, y2, rec


def truncation(x, y, lo: float, hi: float):
    x, y = np.asarray(x, float), np.asarray(y, float)
    m = (x >= lo) & (x <= hi)
    if m.sum() < 3:
        raise ValueError("Truncation range leaves fewer than 3 points.")
    return x[m], y[m], _record("truncation", {"lo": lo, "hi": hi})


_FUNCS = {"axis_shift": axis_shift, "axis_warp": axis_warp, "signal_shift": signal_shift, "broadening": broadening,
          "baseline_distortion": baseline_distortion, "intensity_scale": intensity_scale, "noise": noise,
          "laser_power": laser_power, "temperature": temperature, "truncation": truncation}


def apply(x, y, kind: str, params: dict, seed: int = 0):
    if kind not in _FUNCS:
        raise ValueError(f"Unknown perturbation '{kind}'. Known: {', '.join(sorted(_FUNCS))}.")
    p = dict(params or {})
    if kind in ("noise", "laser_power"):
        p.setdefault("seed", seed)
    try:
        return _FUNCS[kind](x, y, **p)
    except TypeError as e:
        raise ValueError(f"Bad parameters for '{kind}': {e}")


def apply_chain(x, y, steps: list[dict], seed: int = 0):
    """steps: [{kind, params}] applied in order. Returns (x, y, [records])."""
    recs = []
    for i, s in enumerate(steps or []):
        x, y, r = apply(x, y, s["kind"], s.get("params", {}), seed + i)
        recs.append(r)
    return x, y, recs


def resample_to(x_new, x, y):
    """Linear resampling onto x_new; values outside [x[0], x[-1]] are held at the edge value (documented artefact)."""
    return np.interp(x_new, x, y)
