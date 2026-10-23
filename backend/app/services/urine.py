"""Diabetes Urine Study: Raman screening and treatment monitoring from urine spectra.

Two datasets (data/urine/):
- 'zenodo' MEASURED: urine of patients with/without diabetes (Senger et al., Zenodo 10.5281/zenodo.7343559, CC BY 1.0),
  built by scripts/fetch_urine_zenodo.py. Optional: absent until that script has been run.
- 'trial'  SIMULATED: a longitudinal glycaemic-control monitoring trial (data/urine/generate_urine_trial.py).

Everything here is research analysis. Raman spectroscopy measures urine chemistry; it neither diagnoses nor treats
diabetes, and the classifier outputs are cohort similarities, not clinical probabilities.
"""
import csv
import functools
import json

import numpy as np

from . import preprocessing
from .ml import BACKEND, GroupKFold, LogisticRegression, PCA, Pipeline, StandardScaler
from .pipeline import DATA_DIR

URINE_DIR = DATA_DIR / "urine"
DATASETS = ("trial", "zenodo")
DISPLAY_STEP = 2  # every 2nd grid point (4 cm-1) is sent to the browser
N_PCS = 3

# Approximate literature assignments for aqueous urine (785 nm); see data/urine/generate_urine_trial.py.
BANDS = [
    (425, "glucose", "Glucose (skeletal)"), (520, "glucose", "Glucose (C–C–O bend)"), (546, "urea", "Urea"),
    (640, "uric_acid", "Uric acid"), (680, "creatinine", "Creatinine (ring)"), (787, "ketones", "Acetone C–C (ketones)"),
    (843, "creatinine", "Creatinine"), (911, "glucose", "Glucose (C–C)"), (1003, "urea", "Urea C–N stretch"),
    (1060, "glucose", "Glucose (C–O)"), (1125, "glucose", "Glucose C–O–H"), (1160, "urea", "Urea NH₂ rock"),
    (1365, "glucose", "Glucose (CH bend)"), (1420, "creatinine", "Creatinine (CH₃)"), (1450, "albumin", "Protein CH₂"),
    (1625, "urea", "Urea NH₂ bend"), (1655, "albumin", "Protein amide I"), (1710, "ketones", "Ketone C=O"),
]
# Each index is a band height relative to creatinine at 680 cm-1, the usual spot-urine dilution reference.
INDICES = {
    "glucose": {"label": "Glucose index", "bands": (1125, 1060), "note": "Glucose bands at 1125 + 1060 cm⁻¹ / creatinine 680 cm⁻¹"},
    "ketones": {"label": "Ketone index", "bands": (787,), "note": "Acetone band at 787 cm⁻¹ / creatinine 680 cm⁻¹"},
    "urea": {"label": "Urea index", "bands": (1003,), "note": "Urea band at 1003 cm⁻¹ / creatinine 680 cm⁻¹"},
}
REFERENCE_BAND = 680
GROUP_LABELS = {"control": "Normoglycaemic control", "diabetes": "Type 2 diabetes", "healthy": "Healthy volunteers",
                "non_diabetic_ckd": "CKD without diabetes", "diabetic": "Diabetes (with CKD)"}
POSITIVE = {"trial": "diabetes", "zenodo": "diabetic"}
DISCLAIMER = ("Research analysis only, not a diagnostic device: results complement clinical laboratory tests and do not "
              "replace them. Cohort similarity is a model score, not a clinical probability.")


class DatasetUnavailable(ValueError):
    pass


def available() -> list[dict]:
    out = []
    for d in DATASETS:
        m = URINE_DIR / d / "manifest.json"
        if m.exists():
            info = json.loads(m.read_text(encoding="utf-8"))
            out.append({k: info.get(k) for k in ("dataset_id", "name", "category", "excitation_nm", "n_spectra", "license",
                                                  "citation", "doi", "url", "design", "caveat", "groups", "arms")})
    return out


def _read_matrix(d: str):
    folder = URINE_DIR / d
    if d not in DATASETS or not (folder / "spectra.csv").exists():
        raise DatasetUnavailable(f"Dataset '{d}' is not available" + (
            " — run backend/scripts/fetch_urine_zenodo.py to download it." if d == "zenodo" else "."))
    with open(folder / "spectra.csv", encoding="utf-8") as f:
        r = csv.reader(f)
        grid = np.array(next(r)[1:], float)
        ids, rows = [], []
        for line in r:
            ids.append(line[0])
            rows.append(np.array(line[1:], float))
    with open(folder / "samples.csv", encoding="utf-8") as f:
        meta = {m["sample_id"]: m for m in csv.DictReader(f)}
    info = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    return grid, np.array(rows), [_meta(d, meta[i]) for i in ids], info


def _meta(d, m):
    out = dict(m)
    if d == "trial":
        out["group"] = m["arm"]
        out["week"] = int(m["week"])
        out["reference_glucose_mg_dl"] = float(m["glucose_mg_dl"])
    return out


def process(y):
    """Despike + ALS baseline + Savitzky-Golay; returns the baseline-corrected (un-normalised) spectrum."""
    y, _ = preprocessing.despike(np.asarray(y, float))
    out, _, _ = preprocessing.preprocess(y, True, 1e5, 0.01, True, 11, 3, "none")
    return out


def _unit(v):
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


def band_height(x, y, centre, half=8.0, shoulder=22.0):
    """Peak height in centre±half above a straight line through the mean of each shoulder window."""
    core = (x >= centre - half) & (x <= centre + half)
    left = (x >= centre - shoulder) & (x < centre - half)
    right = (x > centre + half) & (x <= centre + shoulder)
    if not core.any() or not left.any() or not right.any():
        return float("nan")
    xl, yl, xr, yr = x[left].mean(), y[left].mean(), x[right].mean(), y[right].mean()
    i = int(np.argmax(y[core]))
    xp = x[core][i]
    base = yl + (yr - yl) * (xp - xl) / (xr - xl)
    return max(0.0, float(y[core][i] - base))


def indices(x, y) -> dict:
    ref = band_height(x, y, REFERENCE_BAND)
    out = {}
    for k, spec in INDICES.items():
        h = sum(band_height(x, y, c) for c in spec["bands"])
        out[k] = round(h / ref, 4) if ref > 0 and np.isfinite(h) else None
    return out


def _classifier(n_train):
    k = int(max(2, min(10, n_train - 2)))
    return Pipeline([("scale", StandardScaler(with_std=False)), ("pca", PCA(n_components=k, svd_solver="full", random_state=0)),
                     ("clf", LogisticRegression(C=1.0, max_iter=2000))])


def _roc(y, p):
    order = np.argsort(-p, kind="stable")
    y = np.asarray(y)[order]
    P, N = y.sum(), (1 - y).sum()
    tpr = np.concatenate([[0], np.cumsum(y) / max(P, 1)])
    fpr = np.concatenate([[0], np.cumsum(1 - y) / max(N, 1)])
    auc = float(np.sum((fpr[1:] - fpr[:-1]) * (tpr[1:] + tpr[:-1]) / 2))
    return fpr, tpr, auc


def classify(X, labels, groups, positive, n_splits=5):
    """Out-of-fold logistic regression on PCA scores; folds never split one participant's samples."""
    y = (np.asarray(labels) == positive).astype(int)
    p = np.zeros(len(y))
    n_splits = int(min(n_splits, len(set(groups))))
    for tr, te in GroupKFold(n_splits=n_splits).split(X, y, groups):
        model = _classifier(len(tr)).fit(X[tr], y[tr])
        p[te] = model.predict_proba(X[te])[:, list(model.named_steps["clf"].classes_).index(1)]
    pred = (p >= 0.5).astype(int)
    tp, fn = int(((pred == 1) & (y == 1)).sum()), int(((pred == 0) & (y == 1)).sum())
    fp, tn = int(((pred == 1) & (y == 0)).sum()), int(((pred == 0) & (y == 0)).sum())
    fpr, tpr, auc = _roc(y, p)
    step = max(1, len(fpr) // 200)
    return {
        "positive": positive, "n": int(len(y)), "n_positive": int(y.sum()), "n_folds": n_splits,
        "method": f"Mean-centring → PCA (≤10 components) → logistic regression; {n_splits}-fold cross-validation grouped "
                  f"by participant ({BACKEND}).",
        "auc": round(auc, 3), "accuracy": round((tp + tn) / len(y), 3),
        "sensitivity": round(tp / max(tp + fn, 1), 3), "specificity": round(tn / max(tn + fp, 1), 3),
        "confusion": {"tp": tp, "fn": fn, "fp": fp, "tn": tn}, "threshold": 0.5,
        "roc": {"fpr": fpr[::step].round(4).tolist() + [1.0], "tpr": tpr[::step].round(4).tolist() + [1.0]},
        "probabilities": p.round(4).tolist(),
    }


def _calibration(ref, idx):
    ref, idx = np.asarray(ref, float), np.asarray(idx, float)
    ok = np.isfinite(ref) & np.isfinite(idx)
    if ok.sum() < 3:
        return None
    slope, intercept = np.polyfit(ref[ok], idx[ok], 1)
    r = float(np.corrcoef(ref[ok], idx[ok])[0, 1])
    return {"slope": float(slope), "intercept": float(intercept), "r": round(r, 3), "r2": round(r * r, 3), "n": int(ok.sum())}


def _trial(meta, idx, Xp_raw, grid):
    weeks = sorted({m["week"] for m in meta})
    people = {}
    for m, ix in zip(meta, idx):
        p = people.setdefault(m["participant"], {"participant": m["participant"], "arm": m["arm"],
                                                 "response": m["response"], "glucose_index": {}, "reference_glucose": {}})
        p["glucose_index"][m["week"]] = ix["glucose"]
        p["reference_glucose"][m["week"]] = m["reference_glucose_mg_dl"]
    cohorts = {"control": "Controls", "responder": "Diabetes · responders", "non-responder": "Diabetes · non-responders"}
    means = []
    for key, label in cohorts.items():
        members = [p for p in people.values() if (p["arm"] if key == "control" else p["response"]) == key]
        vals = np.array([[p["glucose_index"][w] or 0.0 for w in weeks] for p in members])
        means.append({"cohort": key, "label": label, "n": len(members), "mean": vals.mean(axis=0).round(4).tolist(),
                      "se": (vals.std(axis=0, ddof=1) / np.sqrt(len(members))).round(4).tolist()})
    # Mean processed spectrum per visit for responders: the 3D surface of the trial.
    surface = []
    for w in weeks:
        rows = [Xp_raw[i] for i, m in enumerate(meta) if m["response"] == "responder" and m["week"] == w]
        surface.append(np.mean(rows, axis=0)[::DISPLAY_STEP].round(5).tolist())
    responders = [p for p in people.values() if p["response"] == "responder"]
    drop = [1 - p["glucose_index"][weeks[-1]] / p["glucose_index"][weeks[0]] for p in responders if p["glucose_index"][weeks[0]]]
    return {
        "weeks": weeks, "participants": [{**p, "glucose_index": [p["glucose_index"][w] for w in weeks],
                                          "reference_glucose": [p["reference_glucose"][w] for w in weeks]} for p in people.values()],
        "cohort_means": means, "responder_surface": {"weeks": weeks, "grid": grid[::DISPLAY_STEP].tolist(), "z": surface},
        "calibration": _calibration([m["reference_glucose_mg_dl"] for m in meta], [i["glucose"] for i in idx]),
        "responder_median_drop": round(float(np.median(drop)), 3) if drop else None,
    }


@functools.lru_cache(maxsize=4)
def _model(d: str):
    grid, raw, meta, info = _read_matrix(d)
    proc = np.array([process(y) for y in raw])
    Xn = np.array([_unit(v) for v in proc])
    pca = Pipeline([("scale", StandardScaler(with_std=False)), ("pca", PCA(n_components=N_PCS, svd_solver="full", random_state=0))]).fit(Xn)
    labels = [m["group"] for m in meta]
    pos = POSITIVE[d]
    # The trial classifier uses one baseline (week-0) spectrum per participant, so no later visit leaks into training.
    sel = [i for i, m in enumerate(meta) if d != "trial" or m["week"] == 0]
    y = (np.array([labels[i] for i in sel]) == pos).astype(int)
    clf = _classifier(len(sel)).fit(Xn[sel], y)
    return grid, raw, proc, Xn, meta, info, pca, clf, sel


@functools.lru_cache(maxsize=4)
def study(d: str) -> dict:
    grid, raw, proc, Xn, meta, info, pca, clf, sel = _model(d)
    groups = sorted({m["group"] for m in meta}, key=lambda g: (g == POSITIVE[d], g))
    g_disp = grid[::DISPLAY_STEP]
    mean_spectra = []
    for g in groups:
        rows = Xn[[i for i, m in enumerate(meta) if m["group"] == g]]
        mean_spectra.append({"group": g, "label": GROUP_LABELS.get(g, g), "n": len(rows),
                             "mean": rows.mean(axis=0)[::DISPLAY_STEP].round(5).tolist(),
                             "sd": rows.std(axis=0)[::DISPLAY_STEP].round(5).tolist()})
    diff = np.array(mean_spectra[-1]["mean"]) - np.array(mean_spectra[0]["mean"])
    idx = [indices(grid, y) for y in proc]
    scores = pca.transform(Xn)
    evr = pca.named_steps["pca"].explained_variance_ratio_
    loadings = pca.named_steps["pca"].components_[:, ::DISPLAY_STEP]
    cls = classify(Xn[sel], [meta[i]["group"] for i in sel], [meta[i].get("participant", meta[i]["sample_id"]) for i in sel], POSITIVE[d])
    probs = dict(zip(sel, cls.pop("probabilities")))
    # Individual spectra for the 3D waterfall: up to 12 per group, ordered by glucose index.
    waterfall = []
    for g in groups:
        members = [i for i, m in enumerate(meta) if m["group"] == g and (d != "trial" or m["week"] == 0)]
        members = sorted(members, key=lambda i: idx[i]["glucose"] or 0)
        pick = [members[int(k)] for k in np.linspace(0, len(members) - 1, min(12, len(members)))] if members else []
        waterfall += [{"sample_id": meta[i]["sample_id"], "group": g, "glucose_index": idx[i]["glucose"],
                       "y": Xn[i][::DISPLAY_STEP].round(5).tolist()} for i in pick]
    index_stats = {k: {g: _summary([idx[i][k] for i, m in enumerate(meta) if m["group"] == g]) for g in groups} for k in INDICES}
    samples = [{"sample_id": m["sample_id"], "group": m["group"], "week": m.get("week"), "participant": m.get("participant"),
                "response": m.get("response"), "class": m.get("class"), "pc": scores[i].round(5).tolist(),
                "indices": idx[i], "reference_glucose_mg_dl": m.get("reference_glucose_mg_dl"),
                "cv_probability": probs.get(i)} for i, m in enumerate(meta)]
    return {
        "dataset": {k: info.get(k) for k in ("dataset_id", "name", "category", "excitation_nm", "license", "citation", "doi",
                                              "url", "design", "caveat", "instrument", "processing")},
        "n_spectra": len(meta), "groups": [{"id": g, "label": GROUP_LABELS.get(g, g), "n": sum(m["group"] == g for m in meta)} for g in groups],
        "positive_group": POSITIVE[d], "grid": g_disp.tolist(), "mean_spectra": mean_spectra,
        "difference": {"label": f"{mean_spectra[-1]['label']} − {mean_spectra[0]['label']}", "y": diff.round(5).tolist()},
        "bands": [{"position": p, "solute": s, "label": lab} for p, s, lab in BANDS],
        "indices": {k: {**{kk: v for kk, v in spec.items() if kk != "bands"}, "bands": list(spec["bands"])} for k, spec in INDICES.items()},
        "index_stats": index_stats,
        "pca": {"explained_variance_ratio": evr.round(4).tolist(), "loadings": loadings.round(5).tolist()},
        "samples": samples, "classification": cls, "waterfall": waterfall,
        "trial": _trial(meta, idx, Xn, grid) if d == "trial" else None,
        "processing": "Cosmic-ray removal, ALS baseline (λ=1e5, p=0.01), Savitzky–Golay (11, 3), vector normalisation; "
                      "indices from baseline-corrected band heights relative to creatinine (680 cm⁻¹).",
        "disclaimer": DISCLAIMER,
    }


def _summary(v):
    a = np.array([x for x in v if x is not None and np.isfinite(x)], float)
    if not a.size:
        return None
    q = np.percentile(a, [5, 25, 50, 75, 95])
    return {"n": int(a.size), "p5": round(q[0], 4), "q1": round(q[1], 4), "median": round(q[2], 4), "q3": round(q[3], 4),
            "p95": round(q[4], 4), "values": a.round(4).tolist()}


def analyze(x, y, d: str = "trial") -> dict:
    """Places one uploaded urine spectrum relative to a study cohort."""
    grid, raw, proc, Xn, meta, info, pca, clf, sel = _model(d)
    x, y = np.asarray(x, float), np.asarray(y, float)
    lo, hi = max(grid[0], x.min()), min(grid[-1], x.max())
    if lo > 620 or hi < 1700:
        raise ValueError(f"The spectrum covers {x.min():.0f}–{x.max():.0f} cm⁻¹; urine analysis needs at least 620–1700 cm⁻¹ "
                         "(creatinine, glucose and urea bands).")
    order = np.argsort(x)
    yi = np.interp(grid, x[order], y[order])  # values outside the measured range are held at the edge value
    p = process(yi)
    v = _unit(p)
    ix = indices(grid, p)
    sc = pca.transform(v[None, :])[0]
    prob = float(clf.predict_proba(v[None, :])[0, list(clf.named_steps["clf"].classes_).index(1)])
    st = study(d)
    groups = {g["id"]: g["label"] for g in st["groups"]}
    centroids = {g: np.mean([s["pc"] for s in st["samples"] if s["group"] == g], axis=0) for g in groups}
    nearest = min(centroids, key=lambda g: float(np.linalg.norm(sc - centroids[g])))
    position = {}
    for k in INDICES:
        position[k] = {g: (None if ix[k] is None or not (s := st["index_stats"][k][g]) else
                           round(float(np.mean(np.array(s["values"]) <= ix[k])), 3)) for g in groups}
    flags = []
    gi = st["index_stats"]["glucose"]
    ctrl = [g for g in groups if g != POSITIVE[d]]
    if ix["glucose"] is not None and ctrl and all(gi[g] and ix["glucose"] > gi[g]["p95"] for g in ctrl):
        flags.append("Glucose bands are stronger than in 95% of the reference cohort: consistent with glycosuria.")
    ki = st["index_stats"]["ketones"]
    if ix["ketones"] is not None and ctrl and all(ki[g] and ix["ketones"] > ki[g]["p95"] for g in ctrl):
        flags.append("The 787 cm⁻¹ acetone band is elevated: consistent with ketonuria; confirm with a ketone test.")
    if not flags:
        flags.append("No band index lies outside the reference cohort's 95th percentile.")
    return {
        "dataset": d, "dataset_name": info.get("name"), "dataset_category": info.get("category"),
        "grid": grid[::DISPLAY_STEP].tolist(), "processed": v[::DISPLAY_STEP].round(5).tolist(),
        "covered_cm1": [float(lo), float(hi)], "indices": ix, "index_position": position, "pc": sc.round(5).tolist(),
        "nearest_group": nearest, "nearest_group_label": groups[nearest], "similarity_to_positive": round(prob, 3),
        "positive_group": POSITIVE[d], "positive_label": groups.get(POSITIVE[d]), "flags": flags, "disclaimer": DISCLAIMER,
    }


# Within-person biological CV assumed for analytes that controls barely contain, so their spread cannot be measured
# there. An ASSUMPTION, shown in the UI; replace with estimates from repeat samples of stable patients when available.
ASSUMED_CV = {"glucose": 0.20, "ketones": 0.20, "urea": 0.0}


def rcv_at(r: dict, level: float | None) -> float:
    """Reference change value at a baseline level: 1.96·√2·√(SDw² + (CV·level)²)."""
    return float(1.96 * np.sqrt(2) * np.hypot(r["sd_within"], r["cv_assumed"] * (level or 0.0)))


@functools.lru_cache(maxsize=4)
def reference_change(d: str = "trial") -> dict:
    """Ingredients of the reference change value (RCV): the smallest change between two visits of one person that
    exceeds normal visit-to-visit variation. SDw is the pooled within-person SD of the control participants' repeat
    visits (measurement + biological noise at low levels); the proportional part uses ASSUMED_CV."""
    grid, raw, proc, Xn, meta, info, pca, clf, sel = _model(d)
    people = {}
    for i, m in enumerate(meta):
        if m["group"] != POSITIVE[d] and m.get("participant"):
            people.setdefault(m["participant"], []).append(indices(grid, proc[i]))
    people = {p: v for p, v in people.items() if len(v) >= 2}
    if not people:
        raise DatasetUnavailable(f"Dataset '{d}' has no repeat visits, so personal change cannot be assessed.")
    out = {}
    for k in INDICES:
        var = [np.var([v[k] for v in visits if v[k] is not None], ddof=1) for visits in people.values()]
        sd = float(np.sqrt(np.mean(var)))
        out[k] = {"sd_within": round(sd, 4), "cv_assumed": ASSUMED_CV[k], "n_people": len(people),
                  "rcv_at_zero": round(1.96 * np.sqrt(2) * sd, 4)}
    return out


def participant(pid: str, d: str = "trial") -> dict:
    """One person's visits: indices, change from their own baseline judged against the RCV, position against the
    reference cohort, spectra per visit and the path through the cohort's PCA space."""
    grid, raw, proc, Xn, meta, info, pca, clf, sel = _model(d)
    rows = sorted((i for i, m in enumerate(meta) if m.get("participant") == pid), key=lambda i: meta[i].get("week") or 0)
    if not rows:
        raise KeyError(pid)
    rcv = reference_change(d)
    st = study(d)
    ref = [g["id"] for g in st["groups"] if g["id"] != POSITIVE[d]][0]
    ref_label = GROUP_LABELS.get(ref, ref)
    m0 = meta[rows[0]]
    weeks = [meta[i]["week"] for i in rows]
    idx = [indices(grid, proc[i]) for i in rows]
    series, insights = {}, []
    for k, spec in INDICES.items():
        vals = [v[k] for v in idx]
        base, last = vals[0], vals[-1]
        change = None if base is None or last is None else last - base
        r = round(rcv_at(rcv[k], base), 4)
        rng = st["index_stats"][k][ref]
        series[k] = {
            "label": spec["label"], "values": vals, "baseline": base, "latest": last,
            "change": None if change is None else round(change, 4),
            "change_pct": None if change is None or not base else round(change / base, 3),
            "rcv": r, "significant": change is not None and abs(change) > r,
            "reference_range": [rng["p5"], rng["p95"]] if rng else None,
            "in_reference_range": [None if v is None or not rng else bool(v <= rng["p95"]) for v in vals],
        }
    g = series["glucose"]
    if g["change"] is not None:
        if g["significant"] and g["change"] < 0:
            insights.append(f"Glucose index fell {abs(g['change_pct']) * 100:.0f}% from this person's own baseline, more than the "
                            f"±{g['rcv']:.2f} expected from normal visit-to-visit variation at that level.")
        elif g["significant"]:
            insights.append(f"Glucose index rose {g['change_pct'] * 100:.0f}% from this person's baseline, beyond normal "
                            "visit-to-visit variation.")
        else:
            insights.append("Glucose index has not changed beyond normal visit-to-visit variation since baseline.")
        first_in = next((weeks[i] for i, ok in enumerate(g["in_reference_range"]) if ok), None)
        if not g["in_reference_range"][0] and g["in_reference_range"][-1]:
            insights.append(f"Glycosuria resolved: the glucose index entered the {ref_label.lower()} reference range by week {first_in}.")
        elif not g["in_reference_range"][-1]:
            insights.append(f"The glucose index is still above the {ref_label.lower()} reference range (95th percentile) at week "
                            f"{weeks[-1]}" + ("; it is improving but not yet normal." if g["significant"] and g["change"] < 0 else
                                              ". A person-level signal like this is what a clinician would want to review."))
    kt = series["ketones"]
    if kt["in_reference_range"][0] is False:
        insights.append("Ketone bands were raised at baseline" + (" and have since normalised." if kt["in_reference_range"][-1]
                                                                    else " and remain raised; confirm with a ketone test."))
    if m0.get("arm") == "control":
        insights.append("Control participant: these visits define the normal visit-to-visit variation used for everyone.")
    scores = pca.transform(Xn[rows])
    diff = Xn[rows[-1]] - Xn[rows[0]]
    return {
        "participant": pid, "arm": m0.get("arm"), "response": m0.get("response"), "group": m0["group"], "weeks": weeks,
        "reference_group": ref, "reference_label": ref_label, "indices": series, "reference_change": rcv,
        "reference_glucose_mg_dl": [meta[i].get("reference_glucose_mg_dl") for i in rows],
        "grid": grid[::DISPLAY_STEP].tolist(), "spectra": [Xn[i][::DISPLAY_STEP].round(5).tolist() for i in rows],
        "difference": diff[::DISPLAY_STEP].round(5).tolist(), "pc_path": scores.round(5).tolist(), "insights": insights,
        "disclaimer": DISCLAIMER,
    }


def examples() -> list[dict]:
    m = URINE_DIR / "examples" / "manifest.json"
    return json.loads(m.read_text(encoding="utf-8")) if m.exists() else []
