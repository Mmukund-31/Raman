"""Held-out evaluation of reference matching on the curated MEASURED library, and threshold calibration.

Protocol (leave-one-specimen-out):
  * every measured reference spectrum is used once as a query;
  * the query's own spectrum is removed from the library, so it can only match OTHER specimens of its material
    (the curated library guarantees >= 2 independent specimens per material);
  * negative control: the query's whole material is removed, so any 'ok' answer is a false match;
  * the same queries are re-run under realistic perturbations (noise, fluorescence background, calibration offset).
All queries go through pipeline.analyze(), the exact code path used for uploads.

Outputs: data/references_real/evaluation.json, and thresholds.json (min_score / min_score_margin chosen so the
false-match rate among answered queries stays <= TARGET_FMR). quality.py reads thresholds.json when it exists.
"""
import json
from datetime import date

import numpy as np

from . import evaluation_metrics as em, perturbations as P, pipeline, quality
from .validation import Spectrum

TARGET_FMR = 0.05
PERTURBATIONS = [
    ("clean", []),
    ("noise_snr_low", [{"kind": "noise", "params": {"sigma_frac": 0.05}}]),
    ("fluorescence", [{"kind": "baseline_distortion", "params": {"amplitude_frac": 2.0}}]),
    ("axis_offset_5cm", [{"kind": "axis_shift", "params": {"delta_cm1": 5.0}}]),
]
OPTS = {"library": "measured"}


def _query(ref, exclude, steps, seed):
    x, y = np.asarray(ref["x"], float), np.asarray(ref["y"], float)
    if steps:
        x, y, _ = P.apply_chain(x, y, steps, seed)
    a = pipeline.analyze(Spectrum(x, y), ref["id"], "evaluation", None, OPTS,
                         {"category": "measured", "description": "held-out evaluation"}, frozenset(exclude))
    ms = a["matches"]
    names = [m["material"] for m in ms]
    truth = ref["material"]
    score_blocking = ("Highest similarity", "Top candidates", "Only a few of")  # reasons that depend on the thresholds being calibrated
    other = [w for w in quality.assess(a["snr"], ms, [])[1] if not w.startswith(score_blocking)]  # SNR, coverage, ...
    return {"query": ref["id"], "truth": truth, "status": a["status"], "top1": names[0] if names else None,
            "score": ms[0]["score"] if ms else 0.0, "margin": (ms[0]["score"] - ms[1]["score"]) if len(ms) > 1 else 1.0,
            "rank": (names.index(truth) + 1) if truth in names else None, "other_blocking": bool(other),
            "peak_fraction": _peak_fraction(ms[0]) if ms else 0.0,
            "snr": a["snr"]}


def _peak_fraction(m):
    pa = m.get("peak_agreement") or {}
    n = pa.get("reference_peaks_in_overlap") or 0
    return len(pa.get("matched", [])) / n if n else 0.0


def run(perturb=True, seed=0, progress=None) -> dict:
    refs = pipeline.load_references("measured")
    if not refs:
        raise ValueError("The measured library is empty; run scripts/curate_library.py first.")
    by_mat = {}
    for r in refs:
        by_mat.setdefault(r["material"], []).append(r["id"])
    rows = {"positive": {}, "negative": []}
    plist = PERTURBATIONS if perturb else PERTURBATIONS[:1]
    total = len(refs) * (len(plist) + 1)
    k = 0
    for pname, steps in plist:
        out = []
        for i, r in enumerate(refs):
            out.append(_query(r, {r["id"]}, steps, seed + i))
            k += 1
            if progress:
                progress(k, total)
        rows["positive"][pname] = out
    for i, r in enumerate(refs):
        rows["negative"].append(_query(r, set(by_mat[r["material"]]), [], seed + i))
        k += 1
        if progress:
            progress(k, total)
    thr = calibrate(rows["positive"]["clean"], rows["negative"])
    summary = {p: summarise(v, thr) for p, v in rows["positive"].items()}
    neg = summarise_negative(rows["negative"], thr)
    cv = cross_validate(rows["positive"]["clean"], rows["negative"])
    labels = sorted(by_mat)
    clean = rows["positive"]["clean"]
    rep = em.classification_report([q["truth"] for q in clean], [q["top1"] if q["top1"] in by_mat else labels[0] for q in clean], labels)
    return {
        "protocol": "leave-one-specimen-out on the curated measured library; negative control removes the whole material",
        "date": date.today().isoformat(), "software_version": pipeline.VERSION,
        "n_reference_spectra": len(refs), "n_materials": len(by_mat),
        "thresholds": thr, "summary": summary, "negative_control": neg, "cross_validated": cv,
        "classification_ungated": {k: rep[k] for k in ("accuracy", "macro_f1", "n")},
        "per_material": _per_material(clean, thr),
        "reliability_by_score": _bins(clean),
        "limitations": [
            "Queries are curated database spectra (good signal, mostly 532/785 nm, mineral specimens); user spectra of "
            "other sample types, instruments or quality will usually perform worse.",
            "Only materials in the library can be recognised; the negative control estimates how often an absent material "
            "is wrongly named.",
            "Perturbations are simulated and do not cover every instrument effect.",
        ],
        "rows": rows,
    }


def _accept(q, thr):
    return ((not q["other_blocking"]) and q["score"] >= thr["min_score"] and q["margin"] >= thr["min_score_margin"]
            and q.get("peak_fraction", 1.0) >= thr.get("min_peak_fraction", 0.0))


GRID = {"min_score": np.round(np.arange(0.50, 0.995, 0.01), 2), "min_score_margin": np.round(np.arange(0.0, 0.301, 0.01), 2),
        "min_peak_fraction": np.round(np.arange(0.0, 1.001, 0.05), 2)}


def calibrate(pos, neg, target=TARGET_FMR):
    """Grid search over (min_score, min_score_margin, min_peak_fraction): maximise correct answers on positives subject
    to the false-match rate among ALL answered queries (wrong positives + any answered negative control) <= target.
    Ties go to the loosest thresholds, so the rule is not tuned tighter than the data requires."""
    def arr(qs):
        return (np.array([q["score"] for q in qs]), np.array([q["margin"] for q in qs]),
                np.array([q.get("peak_fraction", 1.0) for q in qs]), np.array([not q["other_blocking"] for q in qs]),
                np.array([q["top1"] == q["truth"] for q in qs]))
    ps, pm, pp, pok, pc = arr(pos)
    ns, nm, nnp, nok, _ = arr(neg)
    best = None
    for s in GRID["min_score"]:
        a1, b1 = pok & (ps >= s), nok & (ns >= s)
        for mg in GRID["min_score_margin"]:
            a2, b2 = a1 & (pm >= mg), b1 & (nm >= mg)
            for pf in GRID["min_peak_fraction"]:
                acc, nacc = a2 & (pp >= pf), b2 & (nnp >= pf)
                correct = int((acc & pc).sum())
                answered = int(acc.sum() + nacc.sum())
                fmr = (answered - correct) / answered if answered else 0.0
                key = (correct, -(s + mg + pf))
                if fmr <= target and (best is None or key > best[0]):
                    best = (key, {"min_score": float(s), "min_score_margin": float(mg), "min_peak_fraction": float(pf)}, fmr)
    if best is None:
        t = {"min_score": 0.99, "min_score_margin": 0.3, "min_peak_fraction": 1.0}
        return {**t, "target_false_match_rate": target, "achieved_false_match_rate": None,
                "note": "No threshold set met the target; the strictest set is used."}
    return {**best[1], "target_false_match_rate": target, "achieved_false_match_rate": round(best[2], 4),
            "n_calibration_queries": len(pos) + len(neg)}


def cross_validate(pos, neg, folds=5, target=TARGET_FMR):
    """Honest estimate of the calibrated gate: thresholds are chosen on 4/5 of the materials and scored on the held-out
    fifth (positives and negative controls of one material always share a fold)."""
    mats = sorted({q["truth"] for q in pos})
    fold_of = {m: i % folds for i, m in enumerate(mats)}
    agg = {"answered": 0, "correct": 0, "n": 0, "neg_answered": 0, "neg_n": 0}
    for k in range(folds):
        train_p = [q for q in pos if fold_of[q["truth"]] != k]
        train_n = [q for q in neg if fold_of[q["truth"]] != k]
        t = calibrate(train_p, train_n, target)
        test_p = [q for q in pos if fold_of[q["truth"]] == k]
        test_n = [q for q in neg if fold_of[q["truth"]] == k]
        acc = [q for q in test_p if _accept(q, t)]
        agg["answered"] += len(acc)
        agg["correct"] += sum(q["top1"] == q["truth"] for q in acc)
        agg["n"] += len(test_p)
        agg["neg_answered"] += sum(_accept(q, t) for q in test_n)
        agg["neg_n"] += len(test_n)
    answered_all = agg["answered"] + agg["neg_answered"]
    return {"folds": folds, "grouped_by": "material", "n": agg["n"],
            "answered_fraction": _r(agg["answered"] / agg["n"]),
            "accuracy_when_answered": _r(agg["correct"] / agg["answered"]) if agg["answered"] else None,
            "negative_false_match_rate": _r(agg["neg_answered"] / agg["neg_n"]),
            "false_match_rate_among_answers": _r((answered_all - agg["correct"]) / answered_all) if answered_all else None}


def summarise(qs, thr):
    n = len(qs)
    acc = [q for q in qs if _accept(q, thr)]
    correct = sum(q["top1"] == q["truth"] for q in acc)
    ranks = [q["rank"] for q in qs]
    return {"n": n, "top1_accuracy_ungated": _r(sum(q["top1"] == q["truth"] for q in qs) / n),
            "top5_accuracy_ungated": _r(sum(r is not None and r <= 5 for r in ranks) / n),
            "mrr": _r(float(np.mean([1 / r if r else 0 for r in ranks]))),
            "answered_fraction": _r(len(acc) / n), "accuracy_when_answered": _r(correct / len(acc)) if acc else None,
            "correct_answers": correct, "wrong_answers": len(acc) - correct}


def summarise_negative(qs, thr):
    acc = sum(_accept(q, thr) for q in qs)
    return {"n": len(qs), "false_match_rate": _r(acc / len(qs)), "answered": acc,
            "meaning": "Fraction of queries whose material was absent from the library but which still received an answer."}


def _per_material(qs, thr):
    out = {}
    for q in qs:
        d = out.setdefault(q["truth"], {"n": 0, "answered": 0, "correct": 0, "confused_with": {}})
        d["n"] += 1
        if _accept(q, thr):
            d["answered"] += 1
            d["correct"] += q["top1"] == q["truth"]
        if q["top1"] != q["truth"]:
            d["confused_with"][q["top1"]] = d["confused_with"].get(q["top1"], 0) + 1
    return out


def _bins(qs, edges=(0, 0.6, 0.7, 0.8, 0.9, 0.95, 1.01)):
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        b = [q for q in qs if lo <= q["score"] < hi]
        out.append({"score_range": [lo, min(hi, 1.0)], "n": len(b),
                    "top1_correct_fraction": _r(sum(q["top1"] == q["truth"] for q in b) / len(b)) if b else None})
    return out


def _r(v):
    return None if v is None else round(float(v), 4)


def headline(ev: dict | None) -> str | None:
    """One plain sentence for reports, or None when no evaluation exists."""
    if not ev:
        return None
    # cross-validated figures: the thresholds were not tuned on the spectra they are scored on
    cv = ev.get("cross_validated") or {}
    ans, acc = cv.get("answered_fraction"), cv.get("accuracy_when_answered")
    fmr = cv.get("negative_false_match_rate")
    if ans is None or acc is None:
        c, n = ev["summary"]["clean"], ev["negative_control"]
        ans, acc, fmr = c["answered_fraction"], c["accuracy_when_answered"], n["false_match_rate"]
    if acc is None:
        return None
    return (f"In a held-out test on {ev['summary']['clean']['n']} real reference spectra of {ev['n_materials']} materials, this "
            f"method gave an answer for {ans * 100:.0f}% of them and was right {acc * 100:.0f}% of the time when it did; for "
            f"materials missing from the library it wrongly named one {fmr * 100:.0f}% of the time.")


def load() -> dict | None:
    p = pipeline.DATA_DIR / "references_real" / "evaluation.json"
    if not p.exists():
        return None
    ev = json.loads(p.read_text(encoding="utf-8"))
    ev.pop("rows", None)
    return ev
