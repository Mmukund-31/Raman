import numpy as np
from scipy.signal import find_peaks


def detect_peaks(x, y, prominence_frac: float = 0.05, edge_frac: float = 0.02):
    y = np.asarray(y, float)
    span = np.ptp(y)
    if span <= 0:
        return []
    idx, props = find_peaks(y, prominence=prominence_frac * span)
    lo, hi = x[0], x[-1]
    margin = edge_frac * (hi - lo)
    top = y.max()
    return [{"position": float(x[i]), "height": float(y[i]),
             "relative_height": float(y[i] / top) if top > 0 else 0.0,
             "prominence": float(pr), "near_boundary": bool(x[i] - lo < margin or hi - x[i] < margin)}
            for i, pr in zip(idx, props["prominences"])]
