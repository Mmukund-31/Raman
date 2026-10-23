"""CSV parsing and validation. Pure functions; no HTTP.

`parse_csv` is the strict original parser for the documented CSV layout. `formats.parse_any` accepts the raw exports
found in practice (RRUFF, ROD, JCAMP-DX, delimited text, JSON) and shares the final checks in `finalise`.
"""
import csv
import io
from dataclasses import dataclass, field

import numpy as np

MAX_BYTES = 5 * 1024 * 1024
MIN_POINTS = 50
MAX_DROP_FRAC = 0.05  # tolerant mode drops at most this fraction of unusable rows before rejecting the file
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
    coordinate_input: str = "raman_shift"  # what the file contained: 'raman_shift' | 'wavelength' | 'absolute_wavenumber'
    converted: bool = False  # True only if the axis was converted using an excitation wavelength
    meta: dict = field(default_factory=dict)  # metadata read from the file itself (format, name, excitation, source id)
    extra_y: list[dict] = field(default_factory=list)  # further spectra on the same axis: [{"name", "y"}]


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
    return finalise(np.array(xs), np.array(ys), [], "raman_shift" if xi is not None else "wavelength", excitation_nm)


def finalise(x, y, warnings, coordinate_input, excitation_nm, strict=True, meta=None, extra_y=None) -> Spectrum:
    """Checks shared by every parser: finiteness, size, axis conversion, ordering, duplicates, information content.
    strict=True rejects any defect (original CSV behaviour); strict=False repairs small defects with a warning."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    warnings = list(warnings)
    extra_y = [dict(e, y=np.asarray(e["y"], float)) for e in (extra_y or [])]
    finite = np.isfinite(x) & np.isfinite(y)
    if not finite.all():
        n_bad = int((~finite).sum())
        if strict or n_bad > MAX_DROP_FRAC * x.size:
            raise ValidationError("Data contains NaN or infinite values."
                                  + ("" if strict else f" {n_bad} of {x.size} rows are affected (more than {MAX_DROP_FRAC:.0%})."))
        x, y = x[finite], y[finite]
        extra_y = [dict(e, y=e["y"][finite]) for e in extra_y]
        warnings.append(f"{n_bad} row(s) with missing, NaN or infinite values were dropped.")
    if x.size < MIN_POINTS:
        raise ValidationError(f"Only {x.size} points; at least {MIN_POINTS} are required.")
    converted = False
    if coordinate_input == "wavelength":
        if not excitation_nm or excitation_nm <= 0:
            raise ValidationError("Wavelength input needs a positive excitation wavelength (nm) to convert to Raman shift.")
        if (x <= 0).any():
            raise ValidationError("Wavelengths must be positive.")
        x = 1e7 / excitation_nm - 1e7 / x
        converted = True
        warnings.append(f"Converted wavelength to Raman shift using excitation {excitation_nm:g} nm "
                        "(conversion only; this does not verify instrument calibration).")
    elif coordinate_input == "absolute_wavenumber":
        if not excitation_nm or excitation_nm <= 0:
            raise ValidationError("The x-axis looks like absolute wavenumbers (cm⁻¹ above 5000). Provide the excitation "
                                  "wavelength (nm) so it can be converted to Raman shift.")
        x = 1e7 / excitation_nm - x
        converted = True
        warnings.append(f"Converted absolute wavenumber to Raman shift using excitation {excitation_nm:g} nm "
                        "(conversion only; this does not verify instrument calibration).")
    order = np.argsort(x, kind="stable")
    if not np.array_equal(order, np.arange(x.size)):
        x, y = x[order], y[order]
        extra_y = [dict(e, y=e["y"][order]) for e in extra_y]
        warnings.append("Coordinates were not sorted; data was sorted ascending.")
    if np.any(np.diff(x) == 0):
        if strict:
            raise ValidationError("Duplicate spectral coordinates found.")
        ux, inv = np.unique(x, return_inverse=True)
        counts = np.bincount(inv)
        avg = lambda v: np.bincount(inv, weights=v) / counts
        warnings.append(f"{x.size - ux.size} duplicate coordinate(s) were averaged.")
        x, y = ux, avg(y)
        extra_y = [dict(e, y=avg(e["y"])) for e in extra_y]
        if x.size < MIN_POINTS:
            raise ValidationError(f"Only {x.size} distinct points; at least {MIN_POINTS} are required.")
    if np.ptp(y) == 0:
        raise ValidationError("Intensity is constant; no spectral information.")
    if not strict and x[0] < -50:
        warnings.append("The axis includes negative Raman shifts (anti-Stokes side); only the overlap with references is compared.")
    return Spectrum(x, y, warnings, coordinate_input, converted, dict(meta or {}), extra_y)
