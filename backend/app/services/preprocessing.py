"""Baseline correction, smoothing and normalization. Raw data are never modified."""
import numpy as np
from scipy import sparse
from scipy.signal import savgol_filter
from scipy.sparse.linalg import spsolve


def als_baseline(y: np.ndarray, lam: float = 1e5, p: float = 0.01, n_iter: int = 10) -> np.ndarray:
    n = y.size
    d = sparse.diags([1.0, -2.0, 1.0], [0, 1, 2], shape=(n - 2, n))
    h = lam * (d.T @ d)
    w = np.ones(n)
    z = y
    for _ in range(n_iter):
        z = spsolve((sparse.diags(w) + h).tocsc(), w * y)
        w = p * (y > z) + (1 - p) * (y < z)
    return z


def valid_savgol(n: int, window: int, poly: int) -> tuple[int, int]:
    if window % 2 == 0:
        window += 1
    window = min(window, n if n % 2 else n - 1)
    if poly >= window:
        raise ValueError("Polynomial order must be smaller than the smoothing window.")
    return window, poly


def preprocess(y, baseline=True, lam=1e5, p=0.01, smooth=True, window=11, poly=3, normalize="vector"):
    """Returns (processed, baseline_curve, params). normalize: 'none' | 'vector' | 'max'."""
    y = np.asarray(y, float)
    params = {"baseline": "als" if baseline else "none", "als_lambda": lam, "als_p": p,
              "smoothing": "savgol" if smooth else "none", "normalization": normalize}
    b = als_baseline(y, lam, p) if baseline else np.zeros_like(y)
    out = y - b
    if smooth:
        window, poly = valid_savgol(y.size, window, poly)
        out = savgol_filter(out, window, poly)
        params.update(savgol_window=window, savgol_poly=poly)
    if normalize == "vector":
        norm = np.linalg.norm(out)
        out = out / norm if norm > 0 else out
    elif normalize == "max":
        m = np.max(np.abs(out))
        out = out / m if m > 0 else out
    elif normalize != "none":
        raise ValueError("normalization must be 'none', 'vector' or 'max'.")
    return out, b, params
