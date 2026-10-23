"""CSV parsing and validation. Pure functions; no HTTP."""
import csv
import io
from dataclasses import dataclass, field

import numpy as np

MAX_BYTES = 5 * 1024 * 1024
MIN_POINTS = 50
X_ALIASES = {"raman_shift_cm1", "raman_shift", "shift"}
WL_ALIASES = {"wavelength_nm", "wavelength"}
Y_ALIASES = {"intensity", "counts"}


class ValidationError(ValueError):
    pass


@dataclass
class Spectrum:
    x: np.ndarray
    y: np.ndarray
    warnings: list[str] = field(default_factory=list)
    coordinate_input: str = "raman_shift"  # what the file contained: 'raman_shift' | 'wavelength'
    converted: bool = False  # True only if wavelength was converted using a user-declared excitation wavelength


def parse_csv(raw: bytes, excitation_nm: float | None = None) -> Spectrum:
    if len(raw) > MAX_BYTES:
        raise ValidationError("File exceeds the 5 MB limit.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValidationError("File is not valid UTF-8 text.")
    rows = [r for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]
    if not rows:
        raise ValidationError("File is empty.")
    header = [c.strip().lower() for c in rows[0]]
    xi = next((i for i, h in enumerate(header) if h in X_ALIASES), None)
    wi = next((i for i, h in enumerate(header) if h in WL_ALIASES), None)
    yi = next((i for i, h in enumerate(header) if h in Y_ALIASES), None)
    if yi is None or (xi is None and wi is None):
        raise ValidationError(
            "Missing required columns. Expected 'raman_shift_cm1' (or 'wavelength_nm') and 'intensity'; "
            f"found: {', '.join(header) or 'none'}."
        )
    ci = xi if xi is not None else wi
    xs, ys, bad = [], [], 0
    for r in rows[1:]:
        try:
            xs.append(float(r[ci]))
            ys.append(float(r[yi]))
        except (ValueError, IndexError):
            bad += 1
    if bad:
        raise ValidationError(f"{bad} row(s) contain missing or non-numeric values.")
    x, y = np.array(xs), np.array(ys)
    if not (np.isfinite(x).all() and np.isfinite(y).all()):
        raise ValidationError("Data contains NaN or infinite values.")
    if x.size < MIN_POINTS:
        raise ValidationError(f"Only {x.size} points; at least {MIN_POINTS} are required.")
    warnings: list[str] = []
    converted = False
    if xi is None:
        if not excitation_nm or excitation_nm <= 0:
            raise ValidationError("Wavelength input needs a positive excitation wavelength (nm) to convert to Raman shift.")
        if (x <= 0).any():
            raise ValidationError("Wavelengths must be positive.")
        x = 1e7 / excitation_nm - 1e7 / x
        converted = True
        warnings.append(f"Converted wavelength to Raman shift using user-declared excitation {excitation_nm:g} nm "
                        "(conversion only; this does not verify instrument calibration).")
    order = np.argsort(x, kind="stable")
    if not np.array_equal(order, np.arange(x.size)):
        x, y = x[order], y[order]
        warnings.append("Coordinates were not sorted; data was sorted ascending.")
    if np.any(np.diff(x) == 0):
        raise ValidationError("Duplicate spectral coordinates found.")
    if np.ptp(y) == 0:
        raise ValidationError("Intensity is constant; no spectral information.")
    return Spectrum(x, y, warnings, "raman_shift" if xi is not None else "wavelength", converted)
