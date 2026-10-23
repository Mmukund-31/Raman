"""Shared evaluation metrics. Each measures a different property; none alone proves success."""
import numpy as np
from .matching import cosine


def rmse(a, b) -> float:
    a, b = np.asarray(a, float), np.asarray(b, float)
    return float(np.sqrt(np.mean((a - b) ** 2)))


def mae(a, b) -> float:
    return float(np.mean(np.abs(np.asarray(a, float) - np.asarray(b, float))))


def spectral_angle(a, b) -> float:
    """Spectral Angle Mapper in radians (0 = identical direction). Insensitive to overall scale, like cosine."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    return float(np.arccos(cosine(a, b)))


def dtw_distance(a, b, band: int = 25, step: int = 4) -> float:
    """Length-normalised DTW distance with a Sakoe-Chiba band on step-downsampled, unit-max signals.

    DTW can hide genuine peak-position errors by warping them away; report it only alongside peak-position error.
    """
    a = np.asarray(a, float)[::step]
    b = np.asarray(b, float)[::step]
    a = a / (np.max(np.abs(a)) or 1.0)
    b = b / (np.max(np.abs(b)) or 1.0)
    n, m = a.size, b.size
    band = max(band, abs(n - m))
    inf = np.inf
    prev = np.full(m + 1, inf)
    prev[0] = 0.0
    for i in range(1, n + 1):
        cur = np.full(m + 1, inf)
        lo, hi = max(1, i - band), min(m, i + band)
        for j in range(lo, hi + 1):
            cost = abs(a[i - 1] - b[j - 1])
            cur[j] = cost + min(prev[j], cur[j - 1], prev[j - 1])
        prev = cur
    return float(prev[m] / (n + m))


def peak_metrics(target_peaks, est_peaks, tol: float = 10.0) -> dict:
    """Compare detected peaks of an estimate against a target (dicts with position / relative_height).

    peak_position_error: mean |dx| over target peaks that have an estimate peak within +-tol (None if none do).
    peak_preservation_rate: fraction of target peaks that have such an estimate peak.
    intensity_ratio_error: mean |relative_height difference| over matched peaks (heights relative to each spectrum's max).
    """
    if not target_peaks:
        return {"peak_position_error_cm1": None, "peak_preservation_rate": None, "intensity_ratio_error": None,
                "n_target_peaks": 0, "n_matched": 0, "tolerance_cm1": tol, "extra_peaks": len(est_peaks)}
    est_pos = np.array([p["position"] for p in est_peaks], float)
    errs, ratios, used = [], [], set()
    for t in target_peaks:
        if est_pos.size == 0:
            break
        order = np.argsort(np.abs(est_pos - t["position"]))
        for k in order:
            if int(k) in used:
                continue
            if abs(est_pos[k] - t["position"]) <= tol:
                used.add(int(k))
                errs.append(abs(est_pos[k] - t["position"]))
                ratios.append(abs(est_peaks[int(k)]["relative_height"] - t["relative_height"]))
            break
    n = len(target_peaks)
    return {"peak_position_error_cm1": float(np.mean(errs)) if errs else None,
            "peak_preservation_rate": len(errs) / n,
            "intensity_ratio_error": float(np.mean(ratios)) if ratios else None,
            "n_target_peaks": n, "n_matched": len(errs), "tolerance_cm1": tol,
            "extra_peaks": max(0, len(est_peaks) - len(errs))}


def expected_calibration_error(proba, y_true_idx, bins: int = 10) -> float:
    """ECE of the top-class confidence; only meaningful for models that output probabilities."""
    proba = np.asarray(proba, float)
    conf = proba.max(axis=1)
    correct = (proba.argmax(axis=1) == np.asarray(y_true_idx)).astype(float)
    edges = np.linspace(0, 1, bins + 1)
    ece = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi)
        if m.any():
            ece += m.mean() * abs(correct[m].mean() - conf[m].mean())
    return float(ece)


def classification_report(y_true, y_pred, labels, proba=None) -> dict:
    y_true, y_pred = list(y_true), list(y_pred)
    idx = {l: i for i, l in enumerate(labels)}
    cm = np.zeros((len(labels), len(labels)), int)
    for t, p in zip(y_true, y_pred):
        cm[idx[t], idx[p]] += 1
    tp = np.diag(cm).astype(float)
    prec = np.divide(tp, cm.sum(axis=0), out=np.zeros(len(labels)), where=cm.sum(axis=0) > 0)
    rec = np.divide(tp, cm.sum(axis=1), out=np.zeros(len(labels)), where=cm.sum(axis=1) > 0)
    f1 = np.divide(2 * prec * rec, prec + rec, out=np.zeros(len(labels)), where=(prec + rec) > 0)
    out = {
        "accuracy": float(tp.sum() / max(1, cm.sum())),
        "macro_f1": float(f1.mean()),
        "per_class": [{"label": l, "precision": float(prec[i]), "recall": float(rec[i]), "f1": float(f1[i]),
                       "support": int(cm[i].sum())} for i, l in enumerate(labels)],
        "labels": list(labels), "confusion_matrix": cm.tolist(), "n": len(y_true),
    }
    if proba is not None:
        out["expected_calibration_error"] = expected_calibration_error(proba, [idx[t] for t in y_true])
    return out
