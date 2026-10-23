"""Rule-based insights. Every statement is built from a computed metric and carries its evidence, data class and limits.

Levels:
- observed:     a number the software measured on the data in front of it
- supported:    a pattern that held consistently across the tested levels/scenarios, scoped to the stated data class
- hypothesis:   a possible explanation that these data cannot test; includes the test that would be needed
- inconclusive: the data cannot answer the question

Model confidence is never used as evidence. Nothing here asserts chemical or biological causation.
"""
import numpy as np

SIM_LIMIT = "Simulated from a synthetic library: this shows the behaviour of the analysis pipeline, not of a physical instrument."


def _ev(metric, value, unit="", baseline=None, note=""):
    return {"metric": metric, "value": value, "unit": unit, "baseline": baseline, "note": note}


def _ins(iid, level, statement, evidence, data_class, validation, limitations=()):
    return {"id": iid, "level": level, "statement": statement, "evidence": evidence, "data_class": data_class,
            "validation_status": validation, "limitations": list(limitations)}


def _validation(res):
    checks = res.get("self_checks") or []
    failed = [c["name"] for c in checks if c.get("passed") is False]
    if failed:
        return "self-check FAILED: " + "; ".join(failed)
    dc = res.get("data_class")
    base = "pipeline self-checks passed" if checks else "no self-checks run"
    return base + ("; not validated on measured data" if dc != "measured" else "")


def _monotone(vals, tol=0.02, decreasing=True):
    d = np.diff(vals)
    return bool(np.all(d <= tol)) if decreasing else bool(np.all(d >= -tol))


def from_sweep(s):
    dc, val = s["data_class"], _validation(s)
    rows = [r for r in s["rows"] if "error" not in r]
    unit, neutral = s["level_unit"], s["neutral_level"]
    out = []
    base = s["baseline"]
    out.append(_ins("sweep-base", "observed",
                    f"With no perturbation the pipeline's top match was '{base['top1']}' (similarity {base['top1_score']:.2f}, "
                    f"status {base['status']}).",
                    [_ev("reference similarity", round(base["top1_score"], 3), "cosine"), _ev("status", base["status"])], dc, val,
                    [SIM_LIMIT]))
    if s["truth"]:
        for side, label in (("below", "below"), ("above", "above")):
            side_rows = sorted([r for r in rows if (r["level"] < neutral if side == "below" else r["level"] > neutral)],
                               key=lambda r: abs(r["level"] - neutral))
            if len(side_rows) < 3:
                continue
            ts = [r["truth_score"] for r in side_rows]
            far = side_rows[-1]
            out.append(_ins(f"sweep-sim-{side}", "observed",
                            f"At {far['level']:g} {unit} ({label} the unperturbed value) similarity to the true material was "
                            f"{far['truth_score']:.2f}, compared with {base['top1_score']:.2f} unperturbed.",
                            [_ev("reference similarity", round(far["truth_score"], 3), "cosine", round(base["top1_score"], 3))],
                            dc, val, [SIM_LIMIT]))
            if _monotone(ts, decreasing=True):
                out.append(_ins(f"sweep-mono-{side}", "supported",
                                f"In this simulation, similarity to the true material did not increase as the perturbation grew "
                                f"({label} the unperturbed value), over {len(side_rows)} tested levels.",
                                [_ev("levels tested", len(side_rows)), _ev("similarity range", f"{min(ts):.2f}-{max(ts):.2f}", "cosine")],
                                dc, val, [SIM_LIMIT]))
        ff = s["first_failure"]
        if ff:
            txt = "; ".join(f"{k}: first failure at {v['level']:g} {unit} ({v['reason']})" for k, v in ff.items())
            out.append(_ins("sweep-fail", "observed", f"The analysis stopped giving a confirmed correct answer at: {txt}. "
                            "This is where this pipeline's provisional thresholds were crossed in the simulation; it is not an instrument tolerance.",
                            [_ev("first failure", txt)], dc, val, [SIM_LIMIT, "Quality thresholds are provisional heuristics."]))
        else:
            out.append(_ins("sweep-nofail", "inconclusive",
                            f"No failure occurred within the tested range, so the limit of reliability was not found.",
                            [_ev("tested levels", len(rows))], dc, val, ["Test a wider range to locate a limit."]))
        top1_wrong_ok = [r for r in rows if r["top1_correct"] and r["status"] != "ok"]
        if top1_wrong_ok:
            out.append(_ins("sweep-gate", "observed",
                            f"At {len(top1_wrong_ok)} level(s) the best match was still the true material but the quality gate "
                            "reported 'inconclusive', so no identification is shown. The gate is stricter than the raw ranking.",
                            [_ev("levels", [r["level"] for r in top1_wrong_ok], unit)], dc, val, ["Thresholds are provisional."]))
    mp = [r for r in rows if r.get("model_prediction")]
    if mp:
        gate_bad = [r for r in mp if r["status"] != "ok" and r["model_prediction"]["confidence"] > 0.8]
        if gate_bad:
            out.append(_ins("sweep-conf", "observed",
                            f"At {len(gate_bad)} level(s) the demo classifier reported >80% confidence while the reference pipeline "
                            "was inconclusive. Model confidence is not evidence that the result is correct.",
                            [_ev("levels", [r["level"] for r in gate_bad], unit)], dc, val,
                            ["The demo classifier is trained on simulated data only; its probabilities are not calibrated."]))
    if s["kind"] in ("axis_shift", "signal_shift"):
        out.append(_ins("sweep-hyp", "hypothesis",
                        "A real calibration error and a real physical peak shift of the same size would look alike in the reported "
                        "coordinates. Which one occurred cannot be decided from these data.",
                        [], dc, val, ["Needs a calibration standard (e.g. a known band measured in the same session) or instrument metadata."]))
    return out


def from_pca(r):
    dc, val = r["data_class"], _validation(r)
    evr = r["explained_variance_ratio"]
    out = [_ins("pca-var", "observed", f"PC1 and PC2 explain {100 * sum(evr[:2]):.1f}% of the variance "
                f"(PC1 {100 * evr[0]:.1f}%, PC2 {100 * evr[1]:.1f}%); {r['n_components']} components explain {100 * sum(evr):.1f}%.",
                [_ev("explained variance PC1+PC2", round(100 * sum(evr[:2]), 2), "%")], dc, val)]
    for a in r["factor_association"]:
        if a["eta_squared_per_pc"] is None:
            out.append(_ins(f"pca-{a['factor']}", "inconclusive", f"'{a['factor']}' has too few groups to assess.", [], dc, val))
            continue
        eta = a["eta_squared_per_pc"]
        k = int(np.argmax(eta[:3]))
        out.append(_ins(f"pca-{a['factor']}", "observed",
                        f"Group membership by '{a['factor']}' accounts for {100 * eta[k]:.0f}% of the score variance on PC{k + 1}"
                        + (f"; silhouette over PC1-PC2 is {a['silhouette']:.2f}." if a["silhouette"] is not None else "."),
                        [_ev(f"eta^2 PC{k + 1} ({a['factor']})", round(eta[k], 3)),
                         _ev("silhouette (PC1-PC2)", None if a["silhouette"] is None else round(a["silhouette"], 3))],
                        dc, val, ["Association, not causation.", "PCA is unsupervised."]))
    cond = next((a for a in r["factor_association"] if a["factor"] == "condition" and a["eta_squared_per_pc"]), None)
    mat = next((a for a in r["factor_association"] if a["factor"] == "material" and a["eta_squared_per_pc"]), None)
    if cond and mat and max(cond["eta_squared_per_pc"][:3]) > 0.5:
        out.append(_ins("pca-hyp", "hypothesis",
                        "A leading component is strongly associated with acquisition condition, so condition effects may be mixed "
                        "into the material structure.", [], dc, val,
                        ["Confirm with measurements in which condition and material are crossed and the acquisition order is randomised."]))
    for w in r["warnings"]:
        out.append(_ins("pca-warn", "inconclusive", w, [], dc, val))
    return out


def from_benchmark(b):
    dc, val = b["data_class"], "protocol self-checks passed; not validated on measured data"
    out = []
    ran = [m for m in b["models"] if m["status"] == "ran"]
    clean = {m["model"]: m["by_scenario"]["clean (nominal)"] for m in ran}
    if clean and all(v["accuracy"] >= 0.99 for v in clean.values()):
        out.append(_ins("bm-ceiling", "supported",
                        "On clean simulated data every model scored essentially perfectly, so this task cannot rank the models "
                        "(ceiling effect): the five synthetic materials are easy to tell apart.",
                        [_ev(k, round(v["accuracy"], 3), "accuracy") for k, v in clean.items()], dc, val,
                        ["Real spectra from many specimens and instruments are far harder."]))
    for m in ran:
        worst = min(m["by_scenario"].items(), key=lambda kv: kv[1]["accuracy"])
        c = m["by_scenario"]["clean (nominal)"]["accuracy"]
        if worst[1]["accuracy"] < c - 0.05:
            out.append(_ins(f"bm-drop-{m['model']}", "observed",
                            f"{m['model']}: accuracy fell from {c:.2f} (clean) to {worst[1]['accuracy']:.2f} under '{worst[0]}'.",
                            [_ev("accuracy", round(worst[1]["accuracy"], 3), "", round(c, 3)),
                             _ev("macro-F1", round(worst[1]["macro_f1"], 3))], dc, val, [SIM_LIMIT]))
    ood = b["out_of_distribution"]["flagged_fraction_by_scenario"]
    flagged = {k: v for k, v in ood.items() if not k.startswith("clean") and v > 0.5}
    if flagged:
        out.append(_ins("bm-ood", "observed",
                        "The PCA reconstruction-error detector flagged more than half of the test spectra as unlike the training data in: "
                        + ", ".join(flagged) + ".", [_ev(k, round(v, 2), "fraction flagged") for k, v in flagged.items()], dc, val,
                        ["Detector threshold is the 95th percentile of training error; not validated on measured data."]))
    if any(m["status"] != "ran" for m in b["models"] if m["model"] in ("cnn1d", "resnet18_1d")):
        out.append(_ins("bm-deep", "inconclusive", "Deep models were not run, so no claim is made about them (an architecture is available "
                        "as an optional experiment).", [], dc, val))
    return out


def from_translation(t):
    dc, val = t["data_class"], _validation(t)
    out = []
    base = t["fidelity"]["resample_only"]["aggregate"]
    for name, comp in t["comparison_vs_resample_only"].items():
        if name == "shift_and_gain":
            continue
        better = [k for k, v in comp.items() if v and v["improved"]]
        worse = [k for k, v in comp.items() if v and not v["improved"]]
        agg = t["fidelity"][name]["aggregate"]
        out.append(_ins(f"tr-{name}", "observed",
                        f"{name} versus resampling only: improved on {', '.join(better) or 'no metric'}; not improved on "
                        f"{', '.join(worse) or 'no metric'}.",
                        [_ev("cosine", round(agg["cosine"]["mean"], 3), "", round(base["cosine"]["mean"], 3)),
                         _ev("peak position error", round(agg["peak_position_error_cm1"]["mean"], 2) if agg["peak_position_error_cm1"] else None, "cm-1",
                             round(base["peak_position_error_cm1"]["mean"], 2) if base["peak_position_error_cm1"] else None),
                         _ev("peak preservation", round(agg["peak_preservation_rate"]["mean"], 3) if agg["peak_preservation_rate"] else None, "",
                             round(base["peak_preservation_rate"]["mean"], 3) if base["peak_preservation_rate"] else None)],
                        dc, val, ["High cosine similarity alone does not show successful translation."]))
    ds = t.get("downstream")
    if ds:
        up = ds["target_domain_test (upper reference)"]["accuracy"]
        b = ds["source_resample_only (baseline)"]["accuracy"]
        if up - b < 0.02:
            out.append(_ins("tr-ceiling", "inconclusive",
                            "Classification of untranslated source spectra was already as accurate as on target spectra, so this "
                            "benchmark cannot show a downstream benefit of translation.",
                            [_ev("accuracy target", up), _ev("accuracy source baseline", b)], dc, val, ["Ceiling effect on easy synthetic classes."]))
    out.append(_ins("tr-neural", "inconclusive", "No neural translator was evaluated; no paired measured data are available.", [], dc, val))
    return out


def from_conditions(c):
    out = []
    for e in c["experiments"]:
        dc = e["data_class"]
        val = "descriptive comparison; not validated on measured data" if dc != "measured" else "descriptive comparison of user-declared measurements"
        ch = ", ".join(e["changed_parameters"]) or "no recorded parameter"
        ev = [_ev("similarity to baseline", round(e["similarity_to_baseline"], 3), "cosine"),
              _ev("mean peak shift", None if e["mean_delta_position_cm1"] is None else round(e["mean_delta_position_cm1"], 2), "cm-1"),
              _ev("mean width change", None if e["mean_delta_fwhm_cm1"] is None else round(e["mean_delta_fwhm_cm1"], 2), "cm-1"),
              _ev("median peak-height ratio", None if e["median_height_ratio"] is None else round(e["median_height_ratio"], 3), "x")]
        out.append(_ins(f"cond-{e['label']}", "observed",
                        f"'{e['label']}' differs from the baseline in: {ch}. Spectral similarity to the baseline is "
                        f"{e['similarity_to_baseline']:.2f}; {e['n_baseline_peaks_matched']} of {len(e['peak_changes'])} baseline peaks were found again.",
                        ev, dc, val, e["warnings"]))
        if len(e["changed_parameters"]) == 1 and dc == "measured":
            out.append(_ins(f"cond-sup-{e['label']}", "supported",
                            f"Only {e['changed_parameters'][0]} is recorded as different, so the differences are associated with it for this sample "
                            "and setup.", ev, dc, val, ["Other unrecorded factors may still differ; one pair of spectra is not a trend."]))
        elif len(e["changed_parameters"]) > 1:
            out.append(_ins(f"cond-conf-{e['label']}", "inconclusive",
                            "Several parameters differ, so the cause of the spectral difference cannot be attributed.", [], dc, val))
    return out


# ---------------------------------------------------------------- plain-language report sections (A-G)

def report_sections(kind, r):
    """Returns {tested, changed, graph, pca, model, trust, conclusion} as plain strings."""
    dc = r.get("data_class", "unknown")
    real = {"measured": "REAL (user-declared measurements)", "simulated": "SIMULATED", "synthetic_example": "SYNTHETIC EXAMPLE"}.get(dc, dc.upper())
    trust = (f"Data type: {real}. " + ("Nothing here is a physical measurement. " if dc != "measured" else "Origin and calibration are not verified by RamanReach. ")
             + "Reference library: synthetic. Quality thresholds are provisional. " + (_validation(r)) + ".")
    s = dict.fromkeys(["tested", "changed", "graph", "pca", "model", "trust", "conclusion"], "Not part of this study.")
    s["trust"] = trust
    ins = r.get("insights", [])
    obs = [i["statement"] for i in ins if i["level"] in ("observed", "supported")]
    inc = [i["statement"] for i in ins if i["level"] in ("hypothesis", "inconclusive")]
    s["changed"] = " ".join(obs[:4]) or "No measurable change was reported."
    s["conclusion"] = (" ".join(obs[:2]) + " " if obs else "") + (
        "Unresolved: " + " ".join(inc[:2]) if inc else "") + " These results describe this analysis pipeline on these spectra; they do not by themselves show what happens on a physical instrument."
    if kind == "sweep":
        s["tested"] = (f"One spectrum ({r['sample']}; truth label {r['truth'] or 'none'}) was passed through the unchanged analysis pipeline after a simulated "
                       f"'{r['label']}' of increasing size ({r['level_unit']}). Everything else was held fixed.")
        s["graph"] = ("The x-axis is Raman shift in cm-1 (the energy offset from the laser). Each trace is the spectrum after one perturbation; "
                      "the dotted trace is the unperturbed spectrum. Peaks that move sideways show the perturbation; the similarity table shows how well the "
                      "spectrum still matches the true reference.")
        s["model"] = "A small demo classifier (trained on simulated data) is shown only for comparison; its confidence is not evidence of correctness."
    elif kind == "pca":
        s["tested"] = (f"{r['n_spectra']} simulated spectra from {len(set(x['material'] for x in r['scores']))} materials under "
                       f"{len(set(x['condition'] for x in r['scores']))} conditions were preprocessed identically, scaled ('{r['scaling']}') and analysed by PCA.")
        s["graph"] = "Each dot is one spectrum placed by its first two principal components. Colour shows material or condition. Axes show the percent of variance explained."
        s["pca"] = " ".join(i["statement"] for i in ins if i["id"].startswith("pca-"))[:900]
    elif kind == "benchmark":
        s["tested"] = f"Models were compared on {b_counts(r)} simulated spectra using specimen-level train/validation/test splits."
        s["graph"] = "The table lists accuracy and macro-F1 on clean test spectra and on spectra with simulated distribution shifts."
        s["model"] = " ".join(i["statement"] for i in ins if i["id"].startswith("bm-"))[:900]
    elif kind == "translation":
        s["tested"] = "Source-condition spectra were translated toward target-condition spectra with simple documented corrections and compared with resampling only."
        s["graph"] = "The plot shows the target, the untranslated source and the translated spectrum on the same axis."
        s["model"] = "Downstream classification used a PCA+SVM trained on target-domain specimens only."
    elif kind == "conditions":
        s["tested"] = f"A baseline spectrum ({r['baseline']['label']}) was compared with {len(r['experiments'])} other spectrum/spectra."
        s["graph"] = "Overlaid traces show the same material under different recorded conditions; the difference plot shows the processed spectrum minus the baseline."
    return s


def b_counts(r):
    sp = r.get("splits", {})
    return sp.get("train_spectra", 0) + sp.get("val_spectra", 0) + sp.get("test_spectra", 0)
