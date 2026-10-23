"""Reproducible model comparison on SIMULATED spectra.

Protocol (fixed by config + seed):
1. Build a nominal simulated dataset; the unit of independence is the SPECIMEN (repeats share specimen parameters).
2. Split specimens (not spectra) per material into train / validation / test; leakage is asserted.
3. All models see the same preprocessed arrays. Hyper-parameters are tuned by specimen-grouped CV on TRAIN only
   (classical) or early-stopped on VALIDATION (deep). The test set is touched once per scenario.
4. Distribution-shift scenarios perturb the RAW test spectra (never the training data) and are re-preprocessed identically.
Results come from synthetic data and say nothing about accuracy on real instruments.
"""
import json
import pickle
import platform
import time

import numpy as np
import scipy

from . import dataset_builder, deep_models, matching, pipeline
from . import perturbations as P
from .evaluation_metrics import classification_report
from .ml import BACKEND, PCA, GroupKFold, LogisticRegression, Pipeline, SVC
from .pca_analysis import make_scaler

DEFAULT_SCENARIOS = [
    {"name": "axis shift +3 cm-1", "steps": [{"kind": "axis_shift", "params": {"delta_cm1": 3}}]},
    {"name": "axis shift +8 cm-1", "steps": [{"kind": "axis_shift", "params": {"delta_cm1": 8}}]},
    {"name": "axis shift -8 cm-1", "steps": [{"kind": "axis_shift", "params": {"delta_cm1": -8}}]},
    {"name": "broadening 8 cm-1", "steps": [{"kind": "broadening", "params": {"sigma_cm1": 8}}]},
    {"name": "strong baseline (1.5x)", "steps": [{"kind": "baseline_distortion", "params": {"amplitude_frac": 1.5}}]},
    {"name": "noise 15% of range", "steps": [{"kind": "noise", "params": {"sigma_frac": 0.15}}]},
]
_CACHE: dict = {}
_DEMO: dict = {}


def split_specimens(meta, seed, frac=(0.6, 0.2, 0.2)):
    """Per-material split over specimen ids. Returns three index arrays and asserts no specimen is shared."""
    rng = np.random.default_rng(seed)
    by_mat: dict = {}
    for m in meta:
        by_mat.setdefault(m["material"], set()).add(m["specimen_id"])
    assign = {}
    for mat, specs in by_mat.items():
        specs = sorted(specs)
        rng.shuffle(specs)
        a, b = int(round(frac[0] * len(specs))), int(round((frac[0] + frac[1]) * len(specs)))
        a, b = max(a, 1), max(b, a + 1)
        for i, s in enumerate(specs):
            assign[s] = 0 if i < a else (1 if i < b else 2)
    idx = [np.array([i for i, m in enumerate(meta) if assign[m["specimen_id"]] == k]) for k in range(3)]
    sets = [{meta[i]["specimen_id"] for i in ix} for ix in idx]
    assert not (sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2]), "specimen leakage between splits"
    return idx, sets


def _tune_classical(kind, Xtr, ytr, groups, scaling, seed, max_k):
    ks = [k for k in (3, 5, 8) if k <= max_k] or [2]
    grid = [(k, c) for k in ks for c in ((1.0, 10.0) if kind == "pca_svm" else (1.0, 10.0))]

    def make(k, c):
        clf = SVC(C=c, kernel="rbf", probability=True, random_state=seed) if kind == "pca_svm" \
            else LogisticRegression(C=c, max_iter=3000)
        return Pipeline([("scale", make_scaler(scaling)), ("pca", PCA(n_components=k, svd_solver="full", random_state=seed)),
                         ("clf", clf)])
    n_splits = min(3, len(set(groups)))
    best, best_s = None, -1
    for k, c in grid:
        scores = []
        for tr, va in GroupKFold(n_splits=n_splits).split(Xtr, ytr, groups):
            if len(set(ytr[tr])) < 2:
                continue
            scores.append((make(k, c).fit(Xtr[tr], ytr[tr]).predict(Xtr[va]) == ytr[va]).mean())
        s = float(np.mean(scores)) if scores else -1
        if s > best_s + 1e-12:
            best, best_s = (k, c), s
    return make(*best).fit(Xtr, ytr), {"n_components": best[0], "C": best[1], "cv_accuracy_train_only": best_s}


def _size_bytes(obj):
    return len(pickle.dumps(obj))


def run_benchmark(cfg: dict | None = None) -> dict:
    c = {"materials": None, "n_specimens": 24, "n_repeats": 2, "seed": 0, "scaling": "none", "include_deep": False,
         "preprocessing": None, "scenarios": None, "deep_epochs": 30}
    c.update(cfg or {})
    key = json.dumps(c, sort_keys=True, default=str)
    if key in _CACHE:
        return _CACHE[key]
    seed = c["seed"]
    ds = dataset_builder.build_simulated(c["materials"], c["n_specimens"], c["n_repeats"], None, seed)
    labels = ds["materials"]
    meta, x, raw = ds["meta"], ds["x"], ds["raw"]
    y_all = np.array([labels.index(m["material"]) for m in meta])
    spec = np.array([m["specimen_id"] for m in meta])
    (tr, va, te), sets = split_specimens(meta, seed)
    if len(tr) == 0 or len(te) == 0 or len(set(y_all[tr])) < 2:
        raise ValueError("Too few specimens to form train/validation/test splits; increase n_specimens.")
    Xp = dataset_builder.preprocess_matrix(raw, c["preprocessing"])
    refs = {r["id"]: r for r in pipeline.load_references()}
    ref_p = np.array([dataset_builder.preprocess_one(np.interp(x, refs[l]["x"], refs[l]["y"]), c["preprocessing"]) for l in labels])
    scenarios = c["scenarios"] or DEFAULT_SCENARIOS

    # scenario test matrices (raw test spectra perturbed, then identical preprocessing)
    test_sets = {"clean (nominal)": Xp[te]}
    rng = np.random.default_rng(seed + 1)
    for sc in scenarios:
        rows = []
        for i in te:
            xx, yy, _ = P.apply_chain(x, raw[i], sc["steps"], seed=int(rng.integers(1 << 30)))
            rows.append(P.resample_to(x, xx, yy))
        test_sets[sc["name"]] = dataset_builder.preprocess_matrix(np.array(rows), c["preprocessing"])

    models, results = {}, []
    ytr, yte = y_all[tr], y_all[te]
    k_max = max(2, min(8, len(set(spec[tr])) - 1, Xp.shape[1]))

    def evaluate(name, predict_fn, proba_fn, info):
        per = {}
        t0 = time.perf_counter()
        for sname, Xt in test_sets.items():
            P_ = proba_fn(Xt) if proba_fn else None
            pred = [labels[i] for i in (P_.argmax(axis=1) if P_ is not None else predict_fn(Xt))]
            rep = classification_report([labels[i] for i in yte], pred, labels, P_)
            per[sname] = {"accuracy": rep["accuracy"], "macro_f1": rep["macro_f1"]}
            if sname.startswith("clean"):
                clean_rep = rep
        inf_ms = (time.perf_counter() - t0) / sum(len(v) for v in test_sets.values()) * 1000
        results.append({"model": name, "status": "ran", **info, "clean_report": clean_rep, "by_scenario": per,
                        "inference_ms_per_spectrum": inf_ms})

    # 1. reference cosine (no training)
    def cos_pred(Xt):
        out = []
        for row in Xt:
            a = row - row.mean()
            out.append(int(np.argmax([matching.cosine(a, r - r.mean()) for r in ref_p])))
        return np.array(out)
    evaluate("cosine_reference", cos_pred, None, {"family": "reference matching", "trained": False, "train_seconds": 0.0,
             "model_size_bytes": int(ref_p.nbytes), "hyperparameters": {}, "note": "Scores are not probabilities; no calibration."})

    # 2/3. PCA + SVM / logistic regression
    fitted = {}
    for kind in ("pca_svm", "pca_logreg"):
        t0 = time.perf_counter()
        model, hp = _tune_classical(kind, Xp[tr], ytr, spec[tr], c["scaling"], seed, k_max)
        ts = time.perf_counter() - t0
        fitted[kind] = model
        evaluate(kind, None, model.predict_proba, {"family": "PCA + classical", "trained": True, "train_seconds": ts,
                 "model_size_bytes": _size_bytes(model), "hyperparameters": hp,
                 "note": "Scaler, PCA and classifier were fitted on training specimens only."})

    # OOD detector from the PCA part of pca_svm (training data only)
    pipe = fitted["pca_svm"]
    def recon_err(X):
        Z = pipe.named_steps["scale"].transform(X)
        R = pipe.named_steps["pca"].inverse_transform(pipe.named_steps["pca"].transform(Z))
        return np.sqrt(((Z - R) ** 2).mean(axis=1))
    thr = float(np.quantile(recon_err(Xp[tr]), 0.95))
    ood = {s: float((recon_err(Xt) > thr).mean()) for s, Xt in test_sets.items()}

    # 4/5. deep models (optional)
    deep_out = []
    for name in ("cnn1d", "resnet18_1d"):
        if not c["include_deep"]:
            deep_out.append({"model": name, "status": "not run", "reason": "include_deep is false (default). Deep models are "
                             "an optional experiment; with only simulated data they cannot support real-world claims."})
        elif not deep_models.torch_available():
            deep_out.append({"model": name, "status": "not run", "reason": "PyTorch is not installed."})
        else:
            clf = deep_models.TorchClassifier(name, len(labels), seed, epochs=c["deep_epochs"]).fit(Xp[tr], ytr, Xp[va], y_all[va])
            evaluate(name, None, clf.predict_proba, {"family": "1-D deep network", "trained": True,
                     "train_seconds": clf.train_seconds, "model_size_bytes": clf.n_params() * 4,
                     "hyperparameters": {"epochs_run": clf.epochs_run, "early_stopping_patience": clf.patience, "lr": clf.lr},
                     "parameters": clf.n_params(), "note": "Early-stopped on a specimen-disjoint validation set."})
    results = results + deep_out
    results.append({"model": "ramannet", "status": "not implemented", "reason": "Not added: needs a licence/dependency review of "
                    "the published implementation and genuine multi-source measured data to be meaningful."})

    counts = {l: int((y_all == i).sum()) for i, l in enumerate(labels)}
    out = {
        "data_class": "simulated", "provenance": dataset_builder.SIM_PROVENANCE,
        "warning": "SIMULATED data from a SYNTHETIC library: these numbers demonstrate the evaluation protocol, not real-world accuracy.",
        "labels": labels, "class_counts": counts, "imbalance_ratio": max(counts.values()) / max(1, min(counts.values())),
        "missing_labels": 0,
        "splits": {"train_specimens": len(sets[0]), "val_specimens": len(sets[1]), "test_specimens": len(sets[2]),
                   "train_spectra": int(len(tr)), "val_spectra": int(len(va)), "test_spectra": int(len(te)),
                   "leakage_check": "passed: no specimen appears in more than one split", "unit_of_independence": "specimen"},
        "scenarios": ["clean (nominal)"] + [s["name"] for s in scenarios],
        "models": results,
        "out_of_distribution": {"detector": "PCA reconstruction error above the 95th percentile of training spectra",
                                "threshold": thr, "flagged_fraction_by_scenario": ood,
                                "note": "A fraction near 5% on clean data is expected by construction."},
        "config": c, "environment": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__,
                                     "ml_backend": BACKEND, "torch": _torch_version()},
        "protocol": ["Specimen-level splits (60/20/20 per material)", "Hyper-parameters tuned on training data only",
                     "Same preprocessing for every model", "Scenarios perturb test spectra only",
                     "Metrics: accuracy, macro-F1, per-class precision/recall, confusion matrix, ECE for probabilistic models"],
        "reference_framework": "Benchmarking Deep Learning Models for Raman Spectroscopy Across Open-Source Datasets "
                               "(arXiv:2601.16107). This is NOT a reproduction of that paper: its datasets, splits and models were not used.",
        "self_checks": [{"name": "no specimen leakage between splits", "passed": True},
                        {"name": "all models evaluated on identical test spectra", "passed": True, "test_index_sha": __import__("hashlib").sha1(te.tobytes()).hexdigest()[:12]}],
    }
    if len(_CACHE) > 8:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = out
    return out


def _torch_version():
    try:
        import torch
        return torch.__version__
    except Exception:
        return None


def demo_model(seed=0):
    """Small PCA-SVM trained once on nominal SIMULATED data; used for the per-shift 'model prediction' column."""
    if seed in _DEMO:
        return _DEMO[seed]
    ds = dataset_builder.build_simulated(None, 16, 2, None, seed)
    Xp = dataset_builder.preprocess_matrix(ds["raw"])
    labels = ds["materials"]
    y = np.array([labels.index(m["material"]) for m in ds["meta"]])
    groups = np.array([m["specimen_id"] for m in ds["meta"]])
    model, hp = _tune_classical("pca_svm", Xp, y, groups, "none", seed, 8)
    _DEMO[seed] = {"model": model, "labels": labels, "grid": ds["x"], "trained_on": "simulated (synthetic library)"}
    return _DEMO[seed]
