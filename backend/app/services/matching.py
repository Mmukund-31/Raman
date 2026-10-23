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


def signal_fraction(x, y, rng):
    """Share of the sample's band energy (sum of squared baseline-corrected intensity) that lies inside rng."""
    e = np.clip(np.asarray(y, float), 0, None) ** 2
    tot = e.sum()
    if rng is None or tot <= 0:
        return 0.0
    inside = (x >= rng[0]) & (x <= rng[1])
    return float(e[inside].sum() / tot)


def rank_score(m, min_coverage=0.7, min_sample=0.6):
    """Ordering key: cosine, discounted when the comparison covers too little of the reference or of the sample.
    A short overlap can give a high cosine while ignoring most bands; the discount keeps such pairs from ranking first."""
    return m["score"] * min(1.0, m["coverage"] / min_coverage) * min(1.0, m.get("sample_signal_in_overlap", 1.0) / min_sample)


def compare(x, y, refs):
    """refs: dicts with id, name, x, y (processed identically to y). Returns matches sorted by rank_score desc."""
    out = []
    for r in refs:
        rng = overlap_range(x, r["x"])
        extra = {k: r[k] for k in ("material", "category", "source", "source_id", "citation", "excitation_nm") if k in r}
        if rng is None:
            out.append({"reference_id": r["id"], "name": r["name"], "score": 0.0, "coverage": 0.0, "overlap": None,
                        "sample_signal_in_overlap": 0.0, "rank_score": 0.0, **extra})
            continue
        grid = np.arange(rng[0], rng[1] + 1e-9, GRID_STEP)
        a, b = np.interp(grid, x, y), np.interp(grid, r["x"], r["y"])
        a, b = a - a.mean(), b - b.mean()  # compare band shape, not offset
        cov = (rng[1] - rng[0]) / (r["x"][-1] - r["x"][0])
        m = {"reference_id": r["id"], "name": r["name"], "score": cosine(a, b), "coverage": float(cov),
             "overlap": [float(rng[0]), float(rng[1])], "sample_signal_in_overlap": signal_fraction(x, y, rng), **extra}
        m["rank_score"] = rank_score(m)
        out.append(m)
    return sorted(out, key=lambda m: m["rank_score"], reverse=True)


def best_per_material(matches):
    """Several spectra of one material are evidence for one candidate: keep its best-ranked spectrum, so the margin
    check compares different materials rather than two specimens of the same one."""
    seen, out = {}, []
    for m in matches:  # already sorted
        key = m.get("material", m["reference_id"])
        if key in seen:
            seen[key]["n_reference_spectra"] += 1
            continue
        seen[key] = dict(m, material=key, n_reference_spectra=1)
        out.append(seen[key])
    return out


MIX_GAIN = 0.05       # a two-material fit must beat the best single reference by this much in cosine
MIX_MIN_SHARE = 0.2   # and each component must carry at least this share of the fitted intensity


def mixture_check(x, y, refs_by_id, candidates):
    """Is the sample explained much better by two references together than by the best one alone?

    Non-negative least squares fits y ~ a*r1 + b*r2 + c over the common range for every pair of the top candidates.
    Returns None when no pair qualifies, else the best pair with its fit quality and component shares. A positive
    result means a single-material answer would be misleading; it does not prove the sample is that mixture."""
    from scipy.optimize import nnls

    if len(candidates) < 2:
        return None
    single = candidates[0]["score"]
    best = None
    for i in range(len(candidates)):
        for j in range(i + 1, len(candidates)):
            r1, r2 = refs_by_id[candidates[i]["reference_id"]], refs_by_id[candidates[j]["reference_id"]]
            lo, hi = max(x[0], r1["x"][0], r2["x"][0]), min(x[-1], r1["x"][-1], r2["x"][-1])
            if hi - lo < 200:
                continue
            g = np.arange(lo, hi + 1e-9, GRID_STEP)
            a = np.interp(g, x, y)
            A = np.c_[np.interp(g, r1["x"], r1["y"]), np.interp(g, r2["x"], r2["y"]), np.ones_like(g)]
            coef, _ = nnls(A, a)
            fit = A @ coef
            parts = np.array([coef[0] * np.abs(A[:, 0]).sum(), coef[1] * np.abs(A[:, 1]).sum()])
            if parts.sum() <= 0:
                continue
            share = parts / parts.sum()
            sc = cosine(fit - fit.mean(), a - a.mean())
            if best is None or sc > best["fit_score"]:
                best = {"materials": [candidates[i].get("material", candidates[i]["reference_id"]),
                                      candidates[j].get("material", candidates[j]["reference_id"])],
                        "names": [candidates[i]["name"], candidates[j]["name"]], "fit_score": sc,
                        "shares": [float(share[0]), float(share[1])], "single_score": single}
    if best and best["fit_score"] - single >= MIX_GAIN and min(best["shares"]) >= MIX_MIN_SHARE:
        return best
    return None


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
