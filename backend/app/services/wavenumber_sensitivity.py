"""One-parameter-at-a-time perturbation sweeps (Wavenumber Sensitivity Lab and the experiment matrix).

A sweep applies a controlled, SIMULATED perturbation of increasing size to a spectrum and re-runs the unchanged analysis
pipeline. It measures how sensitive the pipeline is; it does not measure how often such errors occur on an instrument.
"""
import numpy as np

from . import perturbations as P
from . import pipeline, preprocessing
from .dataset_builder import preprocess_one  # same preprocessing as the model's training data
from .ml import PCA

DEFAULT_LEVELS = {
    "axis_shift": [-20, -12, -8, -4, -2, 0, 2, 4, 8, 12, 20],
    "signal_shift": [-20, -12, -8, -4, -2, 0, 2, 4, 8, 12, 20],
    "axis_warp": [0, 2, 4, 8, 12, 20],
    "broadening": [0, 2, 4, 8, 12, 20],
    "baseline_distortion": [0, 0.25, 0.5, 1.0, 1.5, 2.5],
    "intensity_scale": [0.1, 0.25, 0.5, 1.0, 2.0, 4.0],
    "noise": [0, 0.01, 0.03, 0.06, 0.1, 0.2],
    "laser_power": [0.1, 0.25, 0.5, 1.0, 2.0, 4.0],
    "truncation": [600, 800, 1000, 1400, 1800, 2200],  # lower bound kept; upper bound = end of range
    "temperature": [-100, -50, -25, 0, 25, 50, 100],
}
NEUTRAL = {"axis_shift": 0, "signal_shift": 0, "axis_warp": 0, "broadening": 0, "baseline_distortion": 0, "noise": 0,
           "intensity_scale": 1.0, "laser_power": 1.0, "truncation": 600, "temperature": 0}
LEVEL_PARAM = {"axis_shift": "delta_cm1", "signal_shift": "delta_cm1", "axis_warp": "amplitude_cm1", "broadening": "sigma_cm1",
               "baseline_distortion": "amplitude_frac", "intensity_scale": "factor", "noise": "sigma_frac",
               "laser_power": "factor", "truncation": "lo", "temperature": "delta_T_K"}
UNIT = {"axis_shift": "cm-1", "signal_shift": "cm-1", "axis_warp": "cm-1", "broadening": "cm-1",
        "baseline_distortion": "fraction of peak-to-peak", "intensity_scale": "x", "noise": "fraction of peak-to-peak",
        "laser_power": "x (power ratio)", "truncation": "cm-1 (lower bound)", "temperature": "K"}
SHIFT_KINDS = ("axis_shift", "signal_shift")


def _reference_pca(opts):
    """2-component PCA fitted on the (synthetic) reference library only; for illustrating where a spectrum lands."""
    refs = pipeline.load_references()
    grid = refs[0]["x"]
    M = np.array([preprocessing.preprocess(np.interp(grid, r["x"], r["y"]), True, 1e5, 0.01, True, 11, 3, "vector")[0]
                  for r in refs])
    k = min(2, len(refs) - 1)
    pca = PCA(n_components=k, svd_solver="full").fit(M)
    return grid, pca, [r["id"] for r in refs], pca.transform(M)


def _match_displacement(base_peaks, peaks, window):
    """Per baseline peak: displacement to the nearest peak of the perturbed spectrum within `window` (None if absent)."""
    pos = np.array([p["position"] for p in peaks])
    out = []
    for b in base_peaks:
        if pos.size:
            j = int(np.argmin(np.abs(pos - b["position"])))
            if abs(pos[j] - b["position"]) <= window:
                out.append(float(pos[j] - b["position"]))
                continue
        out.append(None)
    return out


def sweep(x, y, truth: str | None, kind: str, levels=None, options=None, fixed_params=None, seed=0,
          with_model=False, sample_label="spectrum") -> dict:
    if kind not in P.KINDS or kind not in LEVEL_PARAM:
        raise ValueError(f"Unsupported sweep kind '{kind}'.")
    x, y = np.asarray(x, float), np.asarray(y, float)
    levels = sorted(set(levels)) if levels else DEFAULT_LEVELS[kind]
    if len(levels) > 25:
        raise ValueError("At most 25 levels per sweep.")
    fixed = dict(fixed_params or {})
    if kind == "temperature":
        fixed.setdefault("shift_coeff_cm1_per_K", -0.02)
        fixed.setdefault("broadening_coeff_cm1_per_K", 0.01)
    gx, pca, ref_ids, ref_scores = _reference_pca(options)
    model = None
    if with_model:
        from . import model_benchmark
        model = model_benchmark.demo_model()

    # baseline = unperturbed spectrum through the identical pipeline
    base = pipeline.identify(x, y, options, truth)
    rows = []
    for lv in levels:
        params = {**fixed, LEVEL_PARAM[kind]: lv}
        if kind == "truncation":
            params["hi"] = float(x[-1])
        try:
            xp, yp, rec = P.apply(x, y, kind, params, seed)
            res = pipeline.identify(xp, yp, options, truth)
        except ValueError as e:
            rows.append({"level": lv, "error": str(e)})
            continue
        window = max(15.0, 1.5 * abs(lv)) if kind in SHIFT_KINDS or kind in ("axis_warp", "temperature") else 15.0
        disp = _match_displacement(base["peaks"], res["peaks"], window)
        found = [d for d in disp if d is not None]
        row = {
            "level": lv, "record": rec,
            "x": xp.tolist(), "raw": yp.tolist(), "processed": res["processed"], "processed_x": res["x"],
            "status": res["status"], "snr": res["snr"], "top1": res["top1"], "top1_score": res["top1_score"],
            "truth_score": res.get("truth_score"), "margin": res["margin"], "top1_correct": res["top1"] == truth if truth else None,
            "correct": res.get("correct"), "reasons": res["reasons"][:3],
            "n_peaks": len(res["peaks"]), "n_baseline_peaks_found": len(found), "n_baseline_peaks": len(base["peaks"]),
            "peak_displacements_cm1": disp,
            "mean_peak_displacement_cm1": float(np.mean(found)) if found else None,
            "max_abs_peak_displacement_cm1": float(np.max(np.abs(found))) if found else None,
        }
        # position in the reference-library PCA plane
        proc_on_grid = np.interp(gx, res["x"], res["processed"])
        row["pca_position"] = pca.transform(proc_on_grid[None, :])[0].tolist()
        if model is not None:
            proba = model["model"].predict_proba(preprocess_one(np.interp(model["grid"], xp, yp))[None, :])[0]
            row["model_prediction"] = {"label": model["labels"][int(np.argmax(proba))], "confidence": float(proba.max()),
                                       "trained_on": model["trained_on"], "confidence_is_not_evidence": True}
        rows.append(row)

    ok_rows = [r for r in rows if "error" not in r]
    neutral = NEUTRAL[kind]
    # unreliability: smallest |deviation from neutral| (per side) at which the result is wrong or inconclusive
    bad = [r for r in ok_rows if truth and not r["correct"]]
    first_fail = {}
    for side, sel in (("below", lambda r: r["level"] < neutral), ("above", lambda r: r["level"] > neutral)):
        cand = [r for r in bad if sel(r)]
        if cand:
            r = min(cand, key=lambda r: abs(r["level"] - neutral))
            first_fail[side] = {"level": r["level"], "reason": "inconclusive" if r["status"] != "ok" else f"identified as {r['top1']}"}
    checks = []
    if kind in SHIFT_KINDS:
        errs = [abs(r["mean_peak_displacement_cm1"] - r["level"]) for r in ok_rows
                if r["mean_peak_displacement_cm1"] is not None and r["n_baseline_peaks_found"] >= 3]
        step = float(np.median(np.diff(x)))
        checks.append({"name": "pipeline recovers the injected shift from detected peaks (within one grid step)",
                       "passed": bool(errs) and max(errs) <= step + 1e-9, "value": max(errs) if errs else None,
                       "unit": "cm-1", "criterion": f"max |mean displacement - injected| <= {step:g} cm-1"})
    checks.append({"name": "neutral level reproduces the unperturbed analysis",
                   "passed": any(r["level"] == neutral and r["top1"] == base["top1"] for r in ok_rows) or neutral not in levels,
                   "value": None})
    return {
        "kind": kind, "perturbation_class": P.KINDS[kind]["class"], "label": P.KINDS[kind]["label"],
        "level_unit": UNIT[kind], "level_param": LEVEL_PARAM[kind], "neutral_level": neutral, "fixed_params": fixed,
        "truth": truth, "baseline": {k: base[k] for k in ("status", "snr", "top1", "top1_score", "margin")} | {
            "correct": base.get("correct")},
        "baseline_peaks": base["peaks"], "baseline_processed": base["processed"], "baseline_x": base["x"],
        "baseline_raw": y.tolist(), "baseline_raw_x": x.tolist(),
        "rows": rows, "first_failure": first_fail, "reference_pca": {
            "ids": ref_ids, "scores": ref_scores.tolist(),
            "explained_variance_ratio": pca.explained_variance_ratio_.tolist(),
            "note": "PCA fitted on the 5 synthetic reference spectra only; positions are illustrative."},
        "data_class": "simulated", "sample": sample_label, "seed": seed, "preprocessing": options or "default",
        "self_checks": checks,
        "distinction_note": ("An axis-calibration error moves the x coordinates of an unchanged signal; a physical change moves the "
                             "signal on a fixed axis. In the reported coordinates the two can look the same; only metadata or a "
                             "calibration standard can tell them apart. Nonlinear warping, broadening, baseline distortion and "
                             "intensity scaling are different operations and are swept separately."),
        "limitations": ["Perturbations are simulated, not measured.",
                        "Levels are a configurable test range, not an instrument tolerance.",
                        "Sensitivity to one perturbation says nothing about how often it occurs on a real instrument.",
                        "The reference library is synthetic."],
    }


def experiment_matrix(x, y, truth, kinds=None, options=None, seed=0) -> dict:
    """One-at-a-time sweeps for several perturbation kinds; every other variable is held fixed (the unperturbed spectrum)."""
    kinds = kinds or ["axis_shift", "broadening", "baseline_distortion", "noise", "intensity_scale", "truncation"]
    out = []
    for k in kinds:
        s = sweep(x, y, truth, k, None, options, None, seed)
        ok = [r for r in s["rows"] if "error" not in r]
        out.append({"kind": k, "label": s["label"], "class": s["perturbation_class"], "unit": s["level_unit"],
                    "levels": [r["level"] for r in ok], "truth_score": [r["truth_score"] for r in ok],
                    "correct": [r["correct"] for r in ok], "status": [r["status"] for r in ok],
                    "snr": [r["snr"] for r in ok], "first_failure": s["first_failure"], "neutral": s["neutral_level"]})
    return {"truth": truth, "experiments": out, "data_class": "simulated", "held_constant":
            "everything except the one perturbed parameter in each row", "seed": seed}
