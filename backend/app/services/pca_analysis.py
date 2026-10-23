"""PCA exploration of a spectrum collection with provenance, labels and experimental conditions.

PCA is an UNSUPERVISED, linear dimensionality reduction. Clusters in PC space do not prove chemical differences and PC1/PC2
separation does not guarantee classification accuracy. The module therefore also reports how strongly each metadata factor
(material, condition, ...) is associated with every component, so structure caused by acquisition can be seen.
"""
import numpy as np
from . import dataset_builder
from .ml import PCA, BACKEND, Pipeline, StandardScaler, silhouette_score

SCALINGS = ("none", "standard", "pareto")
MIN_SPECTRA_WARN = 20


class ParetoScaler:
    """Mean-centre and divide each variable by sqrt(std): a compromise between no scaling and unit variance."""

    def fit(self, X, y=None):
        self.mean_ = X.mean(axis=0)
        self.scale_ = np.sqrt(np.where(X.std(axis=0) > 0, X.std(axis=0), 1.0))
        return self

    def transform(self, X):
        return (X - self.mean_) / self.scale_

    def fit_transform(self, X, y=None):
        return self.fit(X, y).transform(X)

    def get_params(self, deep=True):
        return {}


def make_scaler(scaling: str):
    if scaling == "none":
        return StandardScaler(with_std=False)  # mean-centring only
    if scaling == "standard":
        return StandardScaler()
    if scaling == "pareto":
        return ParetoScaler()
    raise ValueError(f"scaling must be one of {', '.join(SCALINGS)}.")


def make_pca_pipeline(scaling: str, n_components: int, seed: int = 0) -> Pipeline:
    """Scaler + PCA as one estimator so that, in a predictive pipeline, both are fitted on training data only."""
    return Pipeline([("scale", make_scaler(scaling)),
                     ("pca", PCA(n_components=n_components, svd_solver="full", random_state=seed))])


def align_to_common_grid(spectra, step: float | None = None, min_points: int = 50):
    """spectra: [(x, y)]. Validates coordinate compatibility and resamples onto the intersection of all ranges.

    Returns (grid, matrix, notes). Raises ValueError if the common range is too small to be meaningful."""
    if not spectra:
        raise ValueError("No spectra supplied.")
    lo, hi = max(s[0][0] for s in spectra), min(s[0][-1] for s in spectra)
    if hi <= lo:
        raise ValueError("Spectra have no common wavenumber range.")
    steps = [float(np.median(np.diff(s[0]))) for s in spectra]
    step = step or max(steps)  # never finer than the coarsest input
    grid = np.arange(lo, hi + 1e-9, step)
    if grid.size < min_points:
        raise ValueError(f"Common range {lo:.0f}-{hi:.0f} cm-1 gives only {grid.size} points; need >= {min_points}.")
    notes = []
    narrowest = min(s[0][-1] - s[0][0] for s in spectra)
    if (hi - lo) < 0.9 * narrowest + 1e-9 and (hi - lo) < narrowest:
        notes.append(f"Common range {lo:.0f}-{hi:.0f} cm-1 is narrower than the narrowest input; ends were discarded.")
    if max(steps) / min(steps) > 1.01:
        notes.append(f"Inputs have different point spacing ({min(steps):.2f}-{max(steps):.2f} cm-1); resampled by linear "
                     f"interpolation to {step:.2f} cm-1.")
    return grid, np.array([np.interp(grid, x, y) for x, y in spectra]), notes


def _eta_squared(scores, groups):
    """Fraction of a component's score variance explained by group membership (between-group SS / total SS)."""
    tot = ((scores - scores.mean()) ** 2).sum()
    if tot == 0:
        return 0.0
    between = sum(len(scores[groups == g]) * (scores[groups == g].mean() - scores.mean()) ** 2 for g in np.unique(groups))
    return float(between / tot)


def factor_association(scores, meta, factors):
    """For each factor: eta^2 per component, and silhouette over the plotted components. Association, not causation."""
    out = []
    for f in factors:
        vals = np.array([str(m.get(f, "")) for m in meta])
        groups = np.unique(vals)
        if len(groups) < 2 or len(groups) >= len(vals):
            out.append({"factor": f, "n_groups": int(len(groups)), "eta_squared_per_pc": None, "silhouette": None,
                        "note": "Needs 2 or more groups with repeated members."})
            continue
        eta = [_eta_squared(scores[:, k], vals) for k in range(scores.shape[1])]
        k2 = min(2, scores.shape[1])
        try:
            sil = float(silhouette_score(scores[:, :k2], vals))
        except ValueError:
            sil = None
        out.append({"factor": f, "n_groups": int(len(groups)), "eta_squared_per_pc": eta, "silhouette": sil, "note": ""})
    return out


def loading_regions(grid, loading, top_frac: float = 0.15, min_gap_cm1: float = 25.0):
    """Wavenumber windows where |loading| is in the top fraction, merged when closer than min_gap_cm1."""
    a = np.abs(loading)
    idx = np.where(a >= np.quantile(a, 1 - top_frac))[0]
    regions, start, prev = [], None, None
    for i in idx:
        if start is None:
            start = prev = i
        elif grid[i] - grid[prev] <= min_gap_cm1:
            prev = i
        else:
            regions.append((start, prev))
            start = prev = i
    if start is not None:
        regions.append((start, prev))
    regions = [{"from": float(grid[a0]), "to": float(grid[b0]), "peak_abs_loading": float(a[a0:b0 + 1].max()),
                "sign": "positive" if loading[a0:b0 + 1][np.argmax(a[a0:b0 + 1])] > 0 else "negative"}
               for a0, b0 in regions]
    return sorted(regions, key=lambda r: -r["peak_abs_loading"])[:6]


def run_pca(grid, matrix, meta, n_components=5, scaling="none", factors=("material", "condition"), seed=0) -> dict:
    """Exploratory PCA on an already-preprocessed (n, L) matrix. meta[i] describes row i; the mapping is preserved."""
    X = np.asarray(matrix, float)
    n, L = X.shape
    if len(meta) != n:
        raise ValueError("meta length must equal the number of spectra.")
    if not np.isfinite(X).all():
        raise ValueError("Matrix contains NaN or infinite values.")
    if n < 3:
        raise ValueError("PCA needs at least 3 spectra.")
    k = int(min(max(n_components, 2), n - 1, L))
    pipe = make_pca_pipeline(scaling, k, seed).fit(X)
    pca = pipe.named_steps["pca"]
    scores = pipe.transform(X)
    warnings = []
    if n < MIN_SPECTRA_WARN:
        warnings.append(f"Only {n} spectra: PCA structure from so few samples is unreliable.")
    labels = [str(m.get("material", "")) for m in meta]
    if len(set(labels)) < 2:
        warnings.append("Fewer than 2 distinct labels: group structure cannot be assessed.")
    elif min(labels.count(l) for l in set(labels)) < 3:
        warnings.append("Some labels have fewer than 3 spectra; association statistics are weak.")
    if scaling == "standard":
        warnings.append("Per-wavenumber standardisation amplifies noise in regions with no signal.")
    assoc = factor_association(scores, meta, factors)
    scale_vec = getattr(pipe.named_steps["scale"], "scale_", None)
    comps = pca.components_
    loadings = []
    for i in range(k):
        loadings.append({"pc": i + 1, "values": comps[i].tolist(),
                         "top_regions": loading_regions(grid, comps[i])})
    recon = pca.inverse_transform(scores)
    recon_err = float(np.sqrt(np.mean((pipe.named_steps["scale"].transform(X) - recon) ** 2)))
    evr = pca.explained_variance_ratio_
    return {
        "grid": np.asarray(grid).tolist(),
        "n_spectra": n, "n_points": L, "n_components": k, "scaling": scaling,
        "explained_variance_ratio": evr.tolist(), "cumulative_variance": np.cumsum(evr).tolist(),
        "scores": [{**{kk: vv for kk, vv in m.items() if kk != "perturbations"},
                    "scores": scores[i].tolist()} for i, m in enumerate(meta)],
        "loadings": loadings, "factor_association": assoc, "warnings": warnings,
        "self_checks": [
            {"name": "explained variance ratios sum to <= 1", "passed": bool(evr.sum() <= 1 + 1e-9), "value": float(evr.sum())},
            {"name": "scores are centred", "passed": bool(np.abs(scores.mean(axis=0)).max() < 1e-6 * (1 + np.abs(scores).max())),
             "value": float(np.abs(scores.mean(axis=0)).max())},
            {"name": "components are orthonormal", "passed": bool(np.allclose(comps @ comps.T, np.eye(k), atol=1e-6)),
             "value": float(np.abs(comps @ comps.T - np.eye(k)).max())},
        ],
        "ml_backend": BACKEND, "reconstruction_rmse": recon_err, "scaling_scale_used": scale_vec is not None,
        "interpretation_note": ("PCA is unsupervised. Groups in the score plot show where the variance lies, not that the "
                                "groups are chemically different, and not that a classifier will separate them."),
    }


def run_on_simulated(build_cfg: dict, preprocessing_opts=None, n_components=5, scaling="none", factors=("material", "condition")):
    ds = dataset_builder.build_simulated(**build_cfg)
    Xp = dataset_builder.preprocess_matrix(ds["raw"], preprocessing_opts)
    out = run_pca(ds["x"], Xp, ds["meta"], n_components, scaling, factors, build_cfg.get("seed", 0))
    out["data_class"] = "simulated"
    out["provenance"] = ds["provenance"]
    out["dataset_config"] = ds["config"]
    out["preprocessing"] = preprocessing_opts or "default"
    return out
