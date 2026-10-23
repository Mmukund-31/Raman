"""Builds SIMULATED spectrum collections from the (synthetic) bundled references, with provenance and grouping.

Every record keeps: spectrum_id, specimen_id (the independence unit for splits), material label, condition and the
exact perturbation records applied. Repeats of one specimen share specimen-level parameters and differ only by noise,
so they must never be split across train and test. Nothing here is a physical measurement.
"""
import numpy as np

from . import perturbations as P
from . import pipeline, preprocessing

SIM_PROVENANCE = {"category": "simulated",
                  "description": "Generated from the SYNTHETIC reference library with controlled perturbations; "
                                 "not a physical measurement."}
DEFAULT_CONDITIONS = [{"name": "nominal", "steps": []}]
MAX_SPECTRA = 3000


def reference_ids() -> list[str]:
    return [r["id"] for r in pipeline.load_references()]


def build_simulated(materials=None, n_specimens=12, n_repeats=2, conditions=None, seed=0,
                    specimen_axis_sd=1.0, specimen_baseline_sd=0.3, specimen_scale_sd=0.2, noise_frac=0.02) -> dict:
    """Return {"x", "raw" (n, L), "meta" (list of dict), "materials", "provenance"}.

    Specimen-level variability (independent per specimen): small axis offset (sd cm-1), baseline height (fraction of
    the reference peak-to-peak), log-normal intensity scale. Condition steps are then applied identically to every
    spectrum in that condition. Axis shifts are applied as calibration errors and resampled to the common grid.
    """
    refs = {r["id"]: r for r in pipeline.load_references()}
    materials = materials or list(refs)
    unknown = [m for m in materials if m not in refs]
    if unknown:
        raise ValueError(f"Unknown material(s): {', '.join(unknown)}.")
    conditions = conditions or DEFAULT_CONDITIONS
    n = len(materials) * n_specimens * n_repeats * len(conditions)
    if n > MAX_SPECTRA:
        raise ValueError(f"Requested {n} spectra; limit is {MAX_SPECTRA}.")
    x0 = refs[materials[0]]["x"]
    rng = np.random.default_rng(seed)
    raws, meta = [], []
    for mat in materials:
        y0 = refs[mat]["y"]
        for s in range(n_specimens):
            sp_id = f"{mat}-s{s:03d}"
            axis_off = rng.normal(0, specimen_axis_sd)
            base_amp = abs(rng.normal(0, specimen_baseline_sd))
            scale = float(np.exp(rng.normal(0, specimen_scale_sd)))
            for cond in conditions:
                for rep in range(n_repeats):
                    x, y, recs = P.apply_chain(x0, y0 * scale, [
                        {"kind": "baseline_distortion", "params": {"amplitude_frac": base_amp}},
                        {"kind": "axis_shift", "params": {"delta_cm1": axis_off}}], seed=0)
                    x, y, recs2 = P.apply_chain(x, y, cond["steps"], seed=int(rng.integers(1 << 30)))
                    if x.size != x0.size:
                        raise ValueError("Range truncation is not supported in matrix datasets (a common range is "
                                         "required); evaluate truncation with a sweep instead.")
                    _, y, rn = P.noise(x, y, noise_frac, int(rng.integers(1 << 30)))
                    y = P.resample_to(x0, x, y)  # back to the common grid; edge-hold artefact documented in P
                    raws.append(y)
                    meta.append({"spectrum_id": f"{sp_id}-{cond['name']}-r{rep}", "specimen_id": sp_id, "material": mat,
                                 "condition": cond["name"], "repeat": rep, "data_class": "simulated",
                                 "perturbations": recs + recs2 + [rn]})
    return {"x": x0, "raw": np.array(raws), "meta": meta, "materials": materials, "provenance": SIM_PROVENANCE,
            "config": {"materials": materials, "n_specimens": n_specimens, "n_repeats": n_repeats, "seed": seed,
                       "conditions": conditions, "specimen_axis_sd": specimen_axis_sd,
                       "specimen_baseline_sd": specimen_baseline_sd, "specimen_scale_sd": specimen_scale_sd,
                       "noise_frac": noise_frac}}


def preprocess_matrix(raw, opts=None):
    """Apply the standard preprocessing to every row, identically. Returns an (n, L) array."""
    o = {"baseline": True, "als_lambda": 1e5, "als_p": 0.01, "smooth": True, "window": 11, "poly": 3,
         "normalize": "vector"}
    o.update(opts or {})
    return np.array([preprocessing.preprocess(r, o["baseline"], o["als_lambda"], o["als_p"], o["smooth"],
                                              o["window"], o["poly"], o["normalize"])[0] for r in raw])


def preprocess_one(y, opts=None):
    return preprocess_matrix(np.asarray(y, float)[None, :], opts)[0]
