"""Generate the SIMULATED urine Raman trial cohort used by the Diabetes Urine Study page.

These spectra are NOT measurements. Each urine spectrum is a weighted sum of Lorentzian bands at approximate literature
positions for the main urinary solutes, scaled by simulated concentrations, plus water, a fluorescence background and
noise. The trial design (arms, visits, response) is invented to demonstrate longitudinal Raman monitoring; it does not
describe any real study, and Raman spectroscopy monitors urine chemistry, it does not treat or cure diabetes.

Band positions (cm-1, approximate, aqueous urine at 785 nm) follow the assignments commonly reported in the urine Raman
literature, e.g. Senger et al./Kavuru et al. (PeerJ 2023, doi:10.7717/peerj.14879; data: Zenodo 10.5281/zenodo.7343559)
and de Sousa Vieira et al. (Bioengineering 2022, doi:10.3390/bioengineering9100500).

Run: py data/urine/generate_urine_trial.py
"""
import json
import pathlib

import numpy as np

OUT = pathlib.Path(__file__).parent / "trial"
EX = pathlib.Path(__file__).parent / "examples"
X = np.arange(400, 1801, 2.0)
SEED = 20261023

# solute: [(centre cm-1, relative height per unit concentration, hwhm cm-1)]
BANDS = {
    "urea":       [(1003, 1.00, 6), (1160, 0.22, 9), (1625, 0.18, 14), (1470, 0.10, 12), (546, 0.08, 10)],
    "creatinine": [(680, 0.55, 7), (843, 0.30, 8), (905, 0.15, 8), (1420, 0.12, 10)],
    "uric_acid":  [(640, 0.35, 8), (1135, 0.10, 10), (1650, 0.08, 12)],
    "glucose":    [(1125, 0.60, 9), (1060, 0.45, 10), (911, 0.30, 9), (520, 0.25, 12), (1365, 0.15, 12), (425, 0.15, 12)],
    "ketones":    [(787, 0.55, 7), (1710, 0.30, 10), (1430, 0.10, 12)],  # acetone / acetoacetate
    "albumin":    [(1655, 0.35, 18), (1450, 0.25, 14), (1003, 0.12, 5), (1250, 0.15, 18)],
    "water":      [(1640, 1.00, 45)],
}
# Typical concentration (mg/dL) giving one unit of band height above; urea is the internal reference.
UNIT = {"urea": 1500.0, "creatinine": 100.0, "uric_acid": 50.0, "glucose": 900.0, "ketones": 80.0, "albumin": 300.0}
VISITS = [0, 4, 8, 12]


def lorentz(bands):
    y = np.zeros_like(X)
    for c, h, w in bands:
        y += h / (1 + ((X - c) / w) ** 2)
    return y


SOLUTE = {k: lorentz(v) for k, v in BANDS.items()}


def spectrum(conc, rng, fluor, noise):
    y = sum(conc[k] / UNIT[k] * SOLUTE[k] for k in UNIT) + 0.25 * SOLUTE["water"]
    base = fluor * (0.6 + 0.9 * np.exp(-(X - 400) / 700)) + 0.15 * (X - 400) / 1400
    return 1000 * (y + base) + rng.normal(0, noise, X.size)


def participant(pid, arm, rng):
    """Returns per-visit concentrations for one simulated participant."""
    dilution = rng.uniform(0.7, 1.3)  # spot urine concentration varies; creatinine-normalised indices remove most of it
    urea, creat, uric = rng.normal(1800, 300), rng.normal(110, 20), rng.normal(45, 10)
    albumin0 = rng.uniform(0, 30)
    if arm == "control":
        g = [rng.uniform(2, 15) for _ in VISITS]
        k = [rng.uniform(0, 3) for _ in VISITS]
        alb = [albumin0] * len(VISITS)
        response = "n/a"
    else:
        g0 = float(np.exp(rng.normal(np.log(1100), 0.35)))  # baseline glycosuria
        responder = rng.random() < 0.7
        half = rng.uniform(3, 6) if responder else rng.uniform(30, 80)  # weeks to halve urinary glucose
        floor = rng.uniform(10, 60) if responder else rng.uniform(300, 600)
        g = [max(floor, g0 * 0.5 ** (w / half)) if responder else g0 * rng.uniform(0.75, 1.05) for w in VISITS]
        k0 = rng.uniform(20, 70) if rng.random() < 0.35 else rng.uniform(0, 6)
        k = [k0 * (0.35 ** (w / 4) if responder else rng.uniform(0.7, 1.0)) for w in VISITS]
        micro = rng.random() < 0.3
        alb = [(rng.uniform(60, 250) if micro else albumin0) * (0.85 if responder and w else 1.0) for w in VISITS]
        response = "responder" if responder else "non-responder"
    rows = []
    for i, w in enumerate(VISITS):
        d = dilution * rng.uniform(0.9, 1.1)
        conc = {"urea": urea * d, "creatinine": creat * d, "uric_acid": uric * d, "glucose": g[i] * d,
                "ketones": k[i] * d, "albumin": alb[i] * d}
        rows.append({"participant": pid, "arm": arm, "response": response, "week": w, "conc": conc})
    return rows


def main():
    rng = np.random.default_rng(SEED)
    OUT.mkdir(exist_ok=True)
    EX.mkdir(exist_ok=True)
    people = [participant(f"C{i + 1:02d}", "control", rng) for i in range(30)]
    people += [participant(f"T{i + 1:02d}", "diabetes", rng) for i in range(40)]
    meta, spectra = [], []
    for visits in people:
        for v in visits:
            sid = f"{v['participant']}_W{v['week']:02d}"
            spectra.append(spectrum(v["conc"], rng, fluor=rng.uniform(0.3, 0.8), noise=rng.uniform(4, 10)))
            meta.append({"sample_id": sid, "participant": v["participant"], "arm": v["arm"], "response": v["response"],
                         "week": v["week"], **{f"{k}_mg_dl": round(c, 1) for k, c in v["conc"].items()}})
    header = "sample_id," + ",".join(f"{x:.0f}" for x in X)
    lines = [header] + [m["sample_id"] + "," + ",".join(f"{v:.2f}" for v in s) for m, s in zip(meta, spectra)]
    (OUT / "spectra.csv").write_text("\n".join(lines) + "\n")
    keys = list(meta[0])
    (OUT / "samples.csv").write_text("\n".join([",".join(keys)] + [",".join(str(m[k]) for k in keys) for m in meta]) + "\n")

    def save(name, conc, desc):
        y = spectrum(conc, rng, 0.5, 6)
        np.savetxt(EX / f"{name}.csv", np.c_[X, y], delimiter=",", header="raman_shift_cm1,intensity", comments="",
                   fmt=["%.1f", "%.2f"])
        return {"sample_id": name, "file": f"{name}.csv", "description": desc, "category": "synthetic", "excitation_nm": 785,
                "units": "raman_shift_cm1", "concentrations_mg_dl": conc}
    base = {"urea": 1800, "creatinine": 110, "uric_acid": 45, "albumin": 10}
    examples = [
        save("urine_healthy_synthetic", {**base, "glucose": 8, "ketones": 1}, "Normoglycaemic urine (no glycosuria)"),
        save("urine_glycosuria_synthetic", {**base, "glucose": 1400, "ketones": 1}, "Uncontrolled diabetes: marked glycosuria"),
        save("urine_ketonuria_synthetic", {**base, "glucose": 1600, "ketones": 70},
             "Glycosuria with ketonuria (acetone/acetoacetate bands)"),
        save("urine_week12_responder_synthetic", {**base, "glucose": 12, "ketones": 1, "albumin": 25},
             "Same profile after 12 weeks of effective glycaemic control"),
    ]
    lic = "Generated by data/urine/generate_urine_trial.py; no third-party data; free to reuse."
    for e in examples:
        e["license"] = lic
    (EX / "manifest.json").write_text(json.dumps(examples, indent=2))
    (OUT / "manifest.json").write_text(json.dumps({
        "dataset_id": "trial", "name": "Simulated glycaemic-control monitoring trial", "category": "synthetic",
        "excitation_nm": 785, "range_cm1": [float(X[0]), float(X[-1])], "step_cm1": 2.0, "seed": SEED,
        "n_participants": len(people), "n_spectra": len(meta), "visits_weeks": VISITS,
        "arms": {"control": 30, "diabetes": 40},
        "design": "30 normoglycaemic controls and 40 participants with type 2 diabetes and glycosuria, sampled at weeks "
                  "0, 4, 8 and 12 of a glycaemic-control programme; about 70% respond (urinary glucose falls).",
        "bands": BANDS, "unit_concentration_mg_dl": UNIT, "license": lic,
        "source": "Lorentzian bands at approximate literature positions scaled by simulated concentrations; NOT measured.",
    }, indent=2))
    print(f"{len(meta)} spectra, {len(examples)} examples")


if __name__ == "__main__":
    main()
