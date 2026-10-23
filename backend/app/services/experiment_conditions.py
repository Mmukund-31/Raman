"""Experimental Conditions Lab: metadata normalisation and one-baseline-versus-many comparisons.

Spectra here are either user-declared MEASURED data, bundled SYNTHETIC examples or SIMULATED perturbations. The module never
creates measurements for a condition (e.g. a different excitation wavelength) and only reports differences it computed.
Comparisons that change more than one parameter, or whose other parameters are unknown, are flagged as confounded.
"""
import numpy as np
from scipy.signal import peak_widths

from . import peak_detection, pipeline, preprocessing
from .matching import cosine

DATA_CLASSES = ("measured", "simulated", "synthetic_example")
POWER_TO_MW = {"w": 1000.0, "mw": 1.0, "uw": 1e-3, "µw": 1e-3}
KEYS = ["temperature_K", "excitation_nm", "laser_power_mW", "exposure_s", "incidence_angle_deg", "collection_angle_deg",
        "geometry", "instrument", "spot_diameter_um"]


def laser_color(nm: float | None) -> str | None:
    if not nm:
        return None
    for hi, name in ((380, "ultraviolet"), (490, "blue"), (570, "green"), (590, "yellow"), (620, "orange"), (750, "red"),
                     (1e9, "near-infrared")):
        if nm < hi:
            return name


def normalize_metadata(m: dict | None) -> dict:
    """Validate and convert to canonical units (K, nm, mW, s, degrees, um). Unknown values stay None, never guessed."""
    m = dict(m or {})
    out = {k: None for k in KEYS}
    t = m.get("temperature")
    if t is not None:
        unit = str(m.get("temperature_unit", "K")).upper()
        if unit not in ("K", "C"):
            raise ValueError("temperature_unit must be 'K' or 'C'.")
        k = float(t) + (273.15 if unit == "C" else 0.0)
        if k <= 0:
            raise ValueError("Temperature must be above 0 K.")
        out["temperature_K"] = k
    if m.get("excitation_nm") is not None:
        e = float(m["excitation_nm"])
        if not 200 <= e <= 1100:
            raise ValueError("excitation_nm must be between 200 and 1100 nm.")
        out["excitation_nm"] = e
    p = m.get("laser_power")
    if p is not None:
        unit = str(m.get("laser_power_unit", "")).lower()
        if unit not in POWER_TO_MW:
            raise ValueError("laser_power needs an explicit laser_power_unit: 'W', 'mW' or 'uW'.")
        if float(p) <= 0:
            raise ValueError("Laser power must be positive.")
        out["laser_power_mW"] = float(p) * POWER_TO_MW[unit]
    ranges = {"exposure_s": lambda v: v > 0, "spot_diameter_um": lambda v: v > 0,
              "incidence_angle_deg": lambda v: 0 <= v < 90, "collection_angle_deg": lambda v: 0 <= v <= 180}
    for k, ok in ranges.items():
        if m.get(k) is not None:
            v = float(m[k])
            if not ok(v):
                raise ValueError(f"{k} out of range (incidence angle is measured from the surface normal, 0 to <90 degrees).")
            out[k] = v
    for k in ("geometry", "instrument"):
        if m.get(k):
            out[k] = str(m[k])[:80]
    mw, spot = out["laser_power_mW"], out["spot_diameter_um"]
    out["power_density_mW_per_um2"] = None if not (mw and spot) else mw / (np.pi * (spot / 2) ** 2)
    out["laser_color"] = laser_color(out["excitation_nm"])
    return out


def excitation_info(excitation_nm: float, shift_min: float, shift_max: float) -> dict:
    """Scattered wavelengths (nm) for a Raman-shift range: lambda_s = 1e7 / (1e7 / lambda_exc - shift), with lambda in nm and
    shift in cm-1 (1 cm = 1e7 nm). Stokes: positive shift, longer wavelength. Anti-Stokes: same |shift|, shorter wavelength."""
    if not 200 <= excitation_nm <= 1100:
        raise ValueError("excitation_nm must be between 200 and 1100 nm.")
    inv = 1e7 / excitation_nm
    if shift_max >= inv:
        raise ValueError("Raman shift must be smaller than the excitation wavenumber.")
    f = lambda s: 1e7 / (inv - s)
    g = lambda s: 1e7 / (inv + s)  # anti-Stokes: scattered photon gains |shift|
    return {"excitation_nm": excitation_nm, "laser_color": laser_color(excitation_nm),
            "excitation_wavenumber_cm1": inv, "shift_range_cm1": [shift_min, shift_max],
            "stokes_wavelength_nm": [f(shift_min), f(shift_max)],
            "anti_stokes_wavelength_nm": [g(shift_min), g(shift_max)],
            "explanation": ("Excitation wavelength is the colour of the laser. Raman shift is the energy difference between the "
                            "laser light and the scattered light, in cm-1, so the same vibration appears at the same shift for "
                            "every excitation wavelength while the scattered light appears at different wavelengths. A "
                            "spectrum cannot be 'recoloured' to another laser: fluorescence, detector response, resonance "
                            "enhancement and noise change with excitation and need a new measurement.")}


def _fwhm(x, y, idx):
    try:
        w = peak_widths(y, [idx], rel_height=0.5)[0][0]
        return float(w * np.median(np.diff(x)))
    except Exception:
        return None


def _analyse(x, y, options):
    o = {"baseline": True, "als_lambda": 1e5, "als_p": 0.01, "smooth": True, "window": 11, "poly": 3, "normalize": "vector",
         "prominence": 0.05}
    o.update(options or {})
    res = pipeline.identify(x, y, o)
    proc = np.array(res["processed"])
    px = np.array(res["x"])
    idx_of = {p["position"]: int(np.argmin(np.abs(px - p["position"]))) for p in res["peaks"]}
    for p in res["peaks"]:
        p["fwhm_cm1"] = _fwhm(px, proc, idx_of[p["position"]])
    # intensity-preserving pass (baseline removed + smoothed, NOT normalised): comparable only if acquisition matches
    ip, _, _ = preprocessing.preprocess(y, o["baseline"], o["als_lambda"], o["als_p"], o["smooth"], o["window"], o["poly"], "none")
    for p in res["peaks"]:
        p["height_counts"] = float(ip[idx_of[p["position"]]])
    return res, ip, o


def compare(baseline: dict, experiments: list[dict], options=None, truth=None, peak_tol=15.0) -> dict:
    """baseline / experiments: {label, data_class, metadata (raw dict), x, y, perturbations (optional records)}."""
    if not experiments:
        raise ValueError("Provide at least one experiment to compare with the baseline.")
    if len(experiments) > 8:
        raise ValueError("At most 8 comparison experiments.")
    for e in [baseline, *experiments]:
        if e["data_class"] not in DATA_CLASSES:
            raise ValueError(f"data_class must be one of {', '.join(DATA_CLASSES)}.")
        e["meta"] = normalize_metadata(e.get("metadata"))
        e["x"], e["y"] = np.asarray(e["x"], float), np.asarray(e["y"], float)
    b_res, b_ip, o = _analyse(baseline["x"], baseline["y"], options)
    bx, bproc = np.array(b_res["x"]), np.array(b_res["processed"])
    out_exps = []
    for e in experiments:
        res, ip, _ = _analyse(e["x"], e["y"], options)
        ex, eproc = np.array(res["x"]), np.array(res["processed"])
        lo, hi = max(bx[0], ex[0]), min(bx[-1], ex[-1])
        warnings = []
        if hi <= lo:
            raise ValueError(f"'{e['label']}' has no wavenumber overlap with the baseline.")
        grid = np.arange(lo, hi + 1e-9, max(np.median(np.diff(bx)), np.median(np.diff(ex))))
        a, c = np.interp(grid, bx, bproc), np.interp(grid, ex, eproc)
        diff = c - a
        sim = cosine(a - a.mean(), c - c.mean())
        # parameter bookkeeping
        changed, unknown, constant = [], [], []
        for k in KEYS:
            bv, ev = baseline["meta"][k], e["meta"][k]
            if bv is None and ev is None:
                unknown.append(k)
            elif bv is None or ev is None:
                unknown.append(k)
            elif bv != ev:
                changed.append(k)
            else:
                constant.append(k)
        primary = ("temperature_K", "excitation_nm", "laser_power_mW", "exposure_s", "incidence_angle_deg")
        missing = [u for u in unknown if u in primary]
        if not changed:
            design = "no recorded parameter differs"
        elif len(changed) == 1:
            design = "single-parameter change" + (f" (not recorded in both: {', '.join(missing)})" if missing
                                                   else "; other main parameters recorded as equal")
        else:
            design = "multi-parameter change (confounded)"
        if e["data_class"] != "simulated" and len(changed) > 1:
            warnings.append("More than one parameter differs: any spectral difference cannot be attributed to a single cause.")
        if "excitation_nm" in changed:
            warnings.append("Excitation wavelength differs: Raman shifts are comparable, but fluorescence, detector response, "
                            "resonance enhancement and noise can differ. This spectrum cannot be derived from the baseline.")
        if "laser_power_mW" in changed:
            warnings.append("Laser power differs: measured intensity need not scale proportionally (saturation, heating, "
                            "fluorescence, detector). Power is not irradiance unless the spot size is known and equal.")
        if "incidence_angle_deg" in changed or "collection_angle_deg" in changed:
            warnings.append("Geometry differs: there is no universal relation between angle and Raman intensity; it depends on "
                            "material, polarisation, surface and optics. Interpret only as measured for this setup.")
        if "temperature_K" in changed:
            warnings.append("Temperature differs: the effect is material- and mode-specific; do not generalise to other materials.")
        if e["data_class"] == "simulated" or baseline["data_class"] == "simulated":
            warnings.append("At least one spectrum is SIMULATED; differences reflect the chosen perturbation, not a measurement.")
        if e["data_class"] == "synthetic_example" or baseline["data_class"] == "synthetic_example":
            warnings.append("A bundled SYNTHETIC example is used; not a physical measurement.")
        # per-peak changes
        peaks = []
        epos = np.array([p["position"] for p in res["peaks"]])
        for bp in b_res["peaks"]:
            row = {"baseline_position": bp["position"], "matched": False}
            if epos.size:
                j = int(np.argmin(np.abs(epos - bp["position"])))
                if abs(epos[j] - bp["position"]) <= peak_tol:
                    ep = res["peaks"][j]
                    row.update(matched=True, position=ep["position"], delta_position_cm1=ep["position"] - bp["position"],
                               delta_relative_height=ep["relative_height"] - bp["relative_height"],
                               height_ratio=(ep["height_counts"] / bp["height_counts"]) if bp["height_counts"] else None,
                               baseline_fwhm_cm1=bp["fwhm_cm1"], fwhm_cm1=ep["fwhm_cm1"],
                               delta_fwhm_cm1=(ep["fwhm_cm1"] - bp["fwhm_cm1"]) if ep["fwhm_cm1"] is not None and bp["fwhm_cm1"] is not None else None)
            peaks.append(row)
        matched = [p for p in peaks if p["matched"]]
        exp_s, base_s = e["meta"]["exposure_s"], baseline["meta"]["exposure_s"]
        per_second = None
        if exp_s and base_s and matched:
            hr = np.array([p["height_ratio"] for p in matched if p["height_ratio"]])
            if hr.size:
                per_second = float(np.median(hr) / (exp_s / base_s))
        out_exps.append({
            "label": e["label"], "data_class": e["data_class"], "metadata": e["meta"], "perturbations": e.get("perturbations"),
            "changed_parameters": changed, "constant_parameters": constant, "unrecorded_parameters": unknown, "design": design,
            "warnings": warnings, "x": ex.tolist(), "raw": e["y"].tolist(), "raw_x": e["x"].tolist(), "processed": eproc.tolist(),
            "difference_x": grid.tolist(), "difference": diff.tolist(),
            "similarity_to_baseline": sim, "rmse_processed": float(np.sqrt(np.mean(diff ** 2))),
            "snr": res["snr"], "status": res["status"], "top1": res["top1"], "top1_score": res["top1_score"],
            "same_top1_as_baseline": res["top1"] == b_res["top1"],
            "truth_score": res["scores"].get(truth) if truth else None,
            "peak_changes": peaks, "n_peaks": len(res["peaks"]), "n_baseline_peaks_matched": len(matched),
            "median_height_ratio": float(np.median([p["height_ratio"] for p in matched if p["height_ratio"]])) if any(p["height_ratio"] for p in matched) else None,
            "median_height_ratio_per_second": per_second,
            "mean_delta_position_cm1": float(np.mean([p["delta_position_cm1"] for p in matched])) if matched else None,
            "mean_delta_fwhm_cm1": float(np.mean([p["delta_fwhm_cm1"] for p in matched if p["delta_fwhm_cm1"] is not None])) if any(p["delta_fwhm_cm1"] is not None for p in matched) else None,
        })
    return {
        "baseline": {"label": baseline["label"], "data_class": baseline["data_class"], "metadata": baseline["meta"],
                     "x": bx.tolist(), "raw": baseline["y"].tolist(), "raw_x": baseline["x"].tolist(), "processed": bproc.tolist(),
                     "snr": b_res["snr"], "status": b_res["status"], "top1": b_res["top1"], "top1_score": b_res["top1_score"],
                     "peaks": b_res["peaks"]},
        "experiments": out_exps, "truth": truth, "peak_tolerance_cm1": peak_tol, "preprocessing": o,
        "reference_library": "SYNTHETIC (idealised bands)",
        "limitations": ["Differences are computed descriptively; uncontrolled comparisons do not establish causes.",
                        "Reference identification uses the synthetic library and unvalidated quality thresholds.",
                        "Peak height ratios are baseline-corrected counts and are only comparable if acquisition settings match."],
    }
