"""Cosine-similarity reference matching on a common grid over the overlap range."""
import numpy as np

GRID_STEP = 2.0


def overlap_range(x, rx):
    lo, hi = max(x[0], rx[0]), min(x[-1], rx[-1])
    return (lo, hi) if hi > lo else None


def cosine(a, b):
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.clip(np.dot(a, b) / (na * nb), -1.0, 1.0))


def compare(x, y, refs):
    """refs: dicts with id, name, x, y (processed identically to y). Returns matches sorted by score desc."""
    out = []
    for r in refs:
        rng = overlap_range(x, r["x"])
        if rng is None:
            out.append({"reference_id": r["id"], "name": r["name"], "score": 0.0, "coverage": 0.0, "overlap": None})
            continue
        grid = np.arange(rng[0], rng[1] + 1e-9, GRID_STEP)
        a, b = np.interp(grid, x, y), np.interp(grid, r["x"], r["y"])
        a, b = a - a.mean(), b - b.mean()  # compare band shape, not offset
        cov = (rng[1] - rng[0]) / (r["x"][-1] - r["x"][0])
        out.append({"reference_id": r["id"], "name": r["name"], "score": cosine(a, b),
                    "coverage": float(cov), "overlap": [float(rng[0]), float(rng[1])]})
    return sorted(out, key=lambda m: m["score"], reverse=True)


PEAK_TOLERANCE = 10.0  # cm-1; provisional, chosen for readability, not derived from instrument resolution


def peak_agreement(sample_pos, ref_pos, overlap, tol=PEAK_TOLERANCE):
    """Which reference peaks inside the overlap have a detected sample peak within +/- tol cm-1."""
    if overlap is None:
        return {"tolerance_cm1": tol, "reference_peaks_in_overlap": 0, "matched": [], "unmatched_reference": []}
    inside = [p for p in ref_pos if overlap[0] <= p <= overlap[1]]
    matched, unmatched = [], []
    for p in inside:
        near = min(sample_pos, key=lambda s: abs(s - p), default=None)
        if near is not None and abs(near - p) <= tol:
            matched.append({"reference": p, "sample": near})
        else:
            unmatched.append(p)
    return {"tolerance_cm1": tol, "reference_peaks_in_overlap": len(inside), "matched": matched,
            "unmatched_reference": unmatched}
