"""Raman Spectral Translation (RST) evaluation: source-condition spectra -> comparable-to-target representation.

A translated spectrum is NOT a measurement from the target instrument. This module evaluates transparent baselines
(resampling, calibration-standard shift correction, gain matching) on PAIRED spectra. Translation parameters are estimated
only from a calibration-standard pair, never from the spectra being evaluated. With no paired measured data available,
the built-in benchmark is a CONTROLLED-PERTURBATION benchmark on synthetic spectra and says nothing about cross-instrument
generalisation. No neural translator is trained: that needs paired measurements and an independent protocol.
"""
import time

import numpy as np

from . import dataset_builder, model_benchmark, peak_detection
from . import perturbations as P
from .evaluation_metrics import (classification_report, dtw_distance, mae, peak_metrics, rmse, spectral_angle)
from .matching import cosine
from .ml import SVC, Pipeline, PCA
from .pca_analysis import make_scaler

DEFAULT_SOURCE_STEPS = [{"kind": "axis_shift", "params": {"delta_cm1": 6.0}},
                        {"kind": "broadening", "params": {"sigma_cm1": 3.0}},
                        {"kind": "baseline_distortion", "params": {"amplitude_frac": 0.8}}]
TRANSLATORS = ("resample_only", "shift_correction", "shift_and_gain")


def estimate_shift(x, ref, test, search=30.0, step=0.25):
    """Shift d (cm-1) such that test(x + d) best matches ref(x) (cosine on mean-centred signals), with parabolic refinement."""
    ds = np.arange(-search, search + 1e-9, step)
    sc = np.array([cosine(ref - ref.mean(), (lambda t: t - t.mean())(np.interp(x + d, x, test))) for d in ds])
    i = int(np.argmax(sc))
    if 0 < i < len(ds) - 1:
        a, b, c = sc[i - 1], sc[i], sc[i + 1]
        den = a - 2 * b + c
        if den != 0:
            return float(ds[i] + 0.5 * step * (a - c) / den), float(sc[i])
    return float(ds[i]), float(sc[i])


def fit_translator(name, x_t, std_target_raw, std_source_x, std_source_raw, opts):
    """Estimate translator parameters from calibration-standard pairs only."""
    params = {"name": name, "shift_cm1": 0.0, "gain": 1.0, "standard_pairs": int(len(std_target_raw))}
    if name == "resample_only" or len(std_target_raw) == 0:
        return params
    tgt = dataset_builder.preprocess_matrix(std_target_raw, opts).mean(axis=0)
    src = dataset_builder.preprocess_matrix(np.array([np.interp(x_t, std_source_x, r) for r in std_source_raw]), opts).mean(axis=0)
    d, score = estimate_shift(x_t, tgt, src)
    params.update(shift_cm1=d, shift_fit_cosine=score)
    if name == "shift_and_gain":
        from . import preprocessing
        def level(r):
            return float(np.sum(np.clip(r - preprocessing.als_baseline(r), 0, None)))
        g = np.median([level(a) / max(level(np.interp(x_t + d, x_t, np.interp(x_t, std_source_x, b))), 1e-12)
                       for a, b in zip(std_target_raw, std_source_raw)])
        params["gain"] = float(g)
    return params


def apply_translator(params, x_t, x_s, y_s):
    """Source spectrum (x_s, y_s) -> values on the target grid x_t."""
    y = np.interp(x_t, x_s, y_s)
    if params["shift_cm1"]:
        y = np.interp(x_t + params["shift_cm1"], x_t, y)
    return y * params["gain"]


def _fidelity(x, tgt_p, est_p, opts_prom=0.05):
    tp = peak_detection.detect_peaks(x, tgt_p, opts_prom)
    ep = peak_detection.detect_peaks(x, est_p, opts_prom)
    pm = peak_metrics(tp, ep)
    return {"rmse": rmse(tgt_p, est_p), "mae": mae(tgt_p, est_p), "cosine": cosine(tgt_p - tgt_p.mean(), est_p - est_p.mean()),
            "spectral_angle_rad": spectral_angle(tgt_p, est_p), "dtw": dtw_distance(tgt_p, est_p), **pm}


METRIC_DIRECTION = {"rmse": "lower", "mae": "lower", "cosine": "higher", "spectral_angle_rad": "lower", "dtw": "lower",
                    "peak_position_error_cm1": "lower", "peak_preservation_rate": "higher", "intensity_ratio_error": "lower"}


def _aggregate(rows):
    out = {}
    for k in METRIC_DIRECTION:
        v = [r[k] for r in rows if r.get(k) is not None]
        out[k] = {"mean": float(np.mean(v)), "sd": float(np.std(v)), "n": len(v)} if v else None
    return out


def evaluate_translators(x_t, tgt_raw, x_s, src_raw, labels, groups, std_target_raw, std_source_raw, opts=None,
                         train_mask=None, seed=0, translators=TRANSLATORS) -> dict:
    """tgt_raw (n, L) on x_t; src_raw (n, Ls) on x_s; row i of each is the SAME specimen/material (paired).
    train_mask selects rows for the downstream classifier (target domain); the rest are evaluation pairs."""
    n = len(tgt_raw)
    train_mask = np.zeros(n, bool) if train_mask is None else np.asarray(train_mask, bool)
    ev = np.where(~train_mask)[0]
    tgt_p = dataset_builder.preprocess_matrix(tgt_raw, opts)
    translated, fitted, timings = {}, {}, {}
    for name in translators:
        t0 = time.perf_counter()
        fitted[name] = fit_translator(name, x_t, std_target_raw, x_s if len(std_source_raw) else x_s, std_source_raw, opts)
        translated[name] = np.array([apply_translator(fitted[name], x_t, x_s, s) for s in src_raw])
        timings[name] = time.perf_counter() - t0
    trans_p = {k: dataset_builder.preprocess_matrix(v, opts) for k, v in translated.items()}

    fid = {}
    for name in translators:
        rows = [_fidelity(x_t, tgt_p[i], trans_p[name][i]) for i in ev]
        fid[name] = {"aggregate": _aggregate(rows), "per_pair": rows}
    base = fid["resample_only"]["per_pair"] if "resample_only" in fid else None
    comparison = {}
    for name in translators:
        if name == "resample_only" or base is None:
            continue
        comp = {}
        for k, d in METRIC_DIRECTION.items():
            pairs = [(r[k], b[k]) for r, b in zip(fid[name]["per_pair"], base) if r.get(k) is not None and b.get(k) is not None]
            if not pairs:
                comp[k] = None
                continue
            diff = np.array([a - b for a, b in pairs])
            better = (diff < 0) if d == "lower" else (diff > 0)
            comp[k] = {"mean_change_vs_baseline": float(diff.mean()), "fraction_of_pairs_improved": float(better.mean()),
                       "improved": bool(better.mean() > 0.5 and (diff.mean() < 0 if d == "lower" else diff.mean() > 0)),
                       "direction_better": d}
        comparison[name] = comp

    # downstream classification: train on target-domain training rows, test on evaluation rows
    downstream = None
    mats = sorted(set(labels))
    tr = np.where(train_mask)[0]
    if len(tr) >= 6 and len(set(np.array(labels)[tr])) >= 2:
        y = np.array(labels)
        clf = Pipeline([("scale", make_scaler("none")), ("pca", PCA(n_components=min(5, len(tr) - 1), svd_solver="full", random_state=seed)),
                        ("clf", SVC(C=1.0, kernel="rbf", probability=True, random_state=seed))]).fit(tgt_p[tr], y[tr])
        def rep(M):
            pred = clf.predict(M[ev])
            return classification_report(list(y[ev]), list(pred), mats)
        downstream = {"classifier": "PCA + SVM trained on TARGET-domain training specimens only",
                      "target_domain_test (upper reference)": _brief(rep(tgt_p)),
                      **{f"source_{n_}" + (" (baseline)" if n_ == "resample_only" else ""): _brief(rep(trans_p[n_])) for n_ in translators}}
    return {"fitted_parameters": fitted, "fidelity": fid, "comparison_vs_resample_only": comparison, "downstream": downstream,
            "runtime_seconds": timings, "n_evaluation_pairs": int(len(ev)),
            "example": {"x": np.asarray(x_t).tolist(), "target": tgt_p[ev[0]].tolist() if len(ev) else None,
                        "source_resampled": trans_p.get("resample_only", [None])[ev[0]].tolist() if len(ev) and "resample_only" in trans_p else None,
                        "translated": {k: v[ev[0]].tolist() for k, v in trans_p.items() if len(ev)}}}


def _brief(r):
    return {"accuracy": r["accuracy"], "macro_f1": r["macro_f1"], "n": r["n"]}


def run_controlled_benchmark(cfg=None) -> dict:
    c = {"n_specimens": 16, "seed": 0, "source_steps": DEFAULT_SOURCE_STEPS, "source_grid_step": 3.0, "standard": "polypropylene",
         "preprocessing": None, "materials": None}
    c.update(cfg or {})
    seed = c["seed"]
    conds = [{"name": "target", "steps": []}, {"name": "source", "steps": c["source_steps"]}]
    ds = dataset_builder.build_simulated(c["materials"], c["n_specimens"], 1, conds, seed)
    x_t, raw, meta = ds["x"], ds["raw"], ds["meta"]
    if c["standard"] not in ds["materials"]:
        raise ValueError(f"Calibration standard '{c['standard']}' is not among the materials.")
    tgt_i = [i for i, m in enumerate(meta) if m["condition"] == "target" and m["material"] != c["standard"]]
    src_i = [i for i, m in enumerate(meta) if m["condition"] == "source" and m["material"] != c["standard"]]
    assert [meta[i]["specimen_id"] for i in tgt_i] == [meta[i]["specimen_id"] for i in src_i], "pairing broken"
    x_s = np.arange(x_t[0] + 50, x_t[-1] - 50 + 1e-9, c["source_grid_step"])
    tgt, src = raw[tgt_i], np.array([np.interp(x_s, x_t, raw[i]) for i in src_i])
    pm = [meta[i] for i in tgt_i]
    labels = [m["material"] for m in pm]
    # specimen-level split: train rows for the downstream classifier (target domain); evaluation pairs are disjoint specimens
    (tr, va, te), sets = model_benchmark.split_specimens(pm, seed)
    train_mask = np.zeros(len(pm), bool)
    train_mask[np.concatenate([tr, va])] = True
    # independent calibration-standard pairs (separate specimens, never evaluated)
    sd = dataset_builder.build_simulated([c["standard"]], 6, 1, conds, seed + 1000)
    st_t = sd["raw"][[i for i, m in enumerate(sd["meta"]) if m["condition"] == "target"]]
    st_s = np.array([np.interp(x_s, x_t, sd["raw"][i]) for i, m in enumerate(sd["meta"]) if m["condition"] == "source"])
    out = evaluate_translators(x_t, tgt, x_s, src, labels, [m["specimen_id"] for m in pm], st_t, st_s, c["preprocessing"], train_mask, seed)
    injected = [s for s in c["source_steps"] if s["kind"] in ("axis_shift", "signal_shift")]
    inj = sum(s["params"]["delta_cm1"] for s in injected)
    est = out["fitted_parameters"]["shift_correction"]["shift_cm1"]
    out.update({
        "mode": "controlled_perturbation", "data_class": "simulated", "provenance": dataset_builder.SIM_PROVENANCE,
        "warning": "CONTROLLED-PERTURBATION benchmark on SYNTHETIC spectra: shows that the evaluation works, NOT that translation "
                   "generalises across real instruments.",
        "config": c, "calibration_standard": c["standard"], "labels": sorted(set(labels)),
        "source_description": {"steps": c["source_steps"], "grid_step_cm1": c["source_grid_step"],
                               "grid": [float(x_s[0]), float(x_s[-1])]},
        "pairing": {"unit": "specimen", "n_pairs": len(pm), "train_specimens_for_classifier": int(len({pm[i]['specimen_id'] for i in np.where(train_mask)[0]})),
                    "evaluation_specimens": int(len({pm[i]['specimen_id'] for i in np.where(~train_mask)[0]})),
                    "leakage": "evaluation specimens and calibration-standard specimens are disjoint from classifier training specimens"},
        "neural_translation": {"status": "not run", "reason": "A neural translator needs paired measured spectra, a defined target "
                               "transformation and an independent test set. None are available; transparent baselines come first."},
        "self_checks": [{"name": "shift estimate from the calibration standard matches the injected shift (|error| < 1 cm-1)",
                         "passed": abs(est - inj) < 1.0 if injected else None, "value": est, "injected_cm1": inj, "unit": "cm-1",
                         "note": "Estimate d satisfies source(x + d) = target(x); per-specimen axis offsets (sd 1 cm-1) limit precision."}],
        "limitations": ["Source and target are produced from the same synthetic library: no real instrument difference is represented.",
                        "Only shift, gain and resampling are corrected; broadening and baseline are not inverted (deconvolution can invent peaks).",
                        "Cosine similarity alone cannot show that peaks were preserved; see peak metrics and downstream results.",
                        "Gain matching has no effect on L2-normalised spectra, so shift_and_gain equals shift_correction in these metrics."],
    })
    return out
