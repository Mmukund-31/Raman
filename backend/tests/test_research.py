import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import (dataset_builder, deep_models, evaluation_metrics as em, experiment_conditions as ec, insight_generation as ig,
                          model_benchmark as mb, pca_analysis as pa, perturbations as P, pipeline, spectral_translation as st,
                          wavenumber_sensitivity as ws)

client = TestClient(app)
X, Y = pipeline.read_xy(pipeline.DATA_DIR / "examples" / "demo_paracetamol_synthetic.csv")
LEVELS = {"observed", "supported", "hypothesis", "inconclusive"}


def _peak(x, y):
    return x[int(np.argmax(y))]


# ---- perturbations -------------------------------------------------------------------------------------------
def test_axis_shift_moves_coordinates_not_signal():
    x2, y2, rec = P.axis_shift(X, Y, 5.0)
    assert np.allclose(x2, X + 5) and np.array_equal(y2, Y)
    assert rec["class"] == "axis_calibration" and rec["simulated"] is True


def test_signal_shift_moves_peak_on_fixed_axis():
    g = np.arange(600, 1600, 1.0)
    y = np.exp(-((g - 1000) / 8) ** 2)
    x2, y2, rec = P.signal_shift(g, y, 7.0)
    assert np.array_equal(x2, g) and abs(_peak(x2, y2) - 1007) <= 1 and rec["class"] == "physical"


def test_broadening_lowers_peak_and_keeps_area():
    g = np.arange(600, 1600, 1.0)
    y = np.exp(-((g - 1000) / 5) ** 2)
    _, y2, _ = P.broadening(g, y, 6.0)
    assert y2.max() < 0.8 * y.max() and abs(y2.sum() - y.sum()) / y.sum() < 0.02


def test_noise_reproducible_and_truncation_and_unknown():
    a = P.noise(X, Y, 0.05, seed=3)[1]
    assert np.array_equal(a, P.noise(X, Y, 0.05, seed=3)[1]) and not np.array_equal(a, P.noise(X, Y, 0.05, seed=4)[1])
    x2, y2, _ = P.truncation(X, Y, 1000, 1400)
    assert x2.min() >= 1000 and x2.max() <= 1400
    with pytest.raises(ValueError, match="Unknown perturbation"):
        P.apply(X, Y, "magic", {})
    with pytest.raises(ValueError, match="Bad parameters"):
        P.apply(X, Y, "axis_shift", {"wrong": 1})


def test_temperature_uses_user_coefficients_and_says_so():
    g = np.arange(600, 1600, 1.0)
    y = np.exp(-((g - 1000) / 5) ** 2)
    x2, y2, rec = P.temperature(g, y, 50, -0.02, 0.0)
    assert abs(_peak(x2, y2) - 999) <= 1 and "assumption" in rec["note"]


# ---- metrics ---------------------------------------------------------------------------------------------------
def test_basic_metrics_known_values():
    a, b = np.array([1.0, 0, 0]), np.array([0, 1.0, 0])
    assert em.rmse(a, a) == 0 and em.mae(a, b) == pytest.approx(2 / 3)
    assert em.spectral_angle(a, b) == pytest.approx(np.pi / 2) and em.spectral_angle(a, 3 * a) == pytest.approx(0, abs=1e-6)
    assert em.dtw_distance(np.sin(np.linspace(0, 6, 200)), np.sin(np.linspace(0, 6, 200))) == 0


def test_peak_metrics():
    t = [{"position": 1000, "relative_height": 1.0}, {"position": 1500, "relative_height": 0.5}]
    e = [{"position": 1003, "relative_height": 0.9}]
    m = em.peak_metrics(t, e, tol=10)
    assert m["peak_position_error_cm1"] == pytest.approx(3) and m["peak_preservation_rate"] == 0.5
    assert m["intensity_ratio_error"] == pytest.approx(0.1)


def test_classification_report_and_ece():
    r = em.classification_report(["a", "a", "b", "b"], ["a", "b", "b", "b"], ["a", "b"])
    assert r["accuracy"] == 0.75 and r["confusion_matrix"] == [[1, 1], [0, 2]]
    assert r["per_class"][1]["precision"] == pytest.approx(2 / 3) and r["per_class"][1]["recall"] == 1.0
    assert em.expected_calibration_error(np.array([[1.0, 0], [0, 1.0]]), [0, 1]) == 0
    assert em.expected_calibration_error(np.array([[1.0, 0], [1.0, 0]]), [0, 1]) == pytest.approx(0.5)


# ---- conditions ------------------------------------------------------------------------------------------------
def test_metadata_units_and_validation():
    m = ec.normalize_metadata({"temperature": 25, "temperature_unit": "C", "laser_power": 5, "laser_power_unit": "mW",
                               "excitation_nm": 633, "incidence_angle_deg": 30})
    assert m["temperature_K"] == pytest.approx(298.15) and m["laser_color"] == "red"
    assert ec.normalize_metadata({"laser_power": 1, "laser_power_unit": "W"})["laser_power_mW"] == 1000
    with pytest.raises(ValueError, match="explicit laser_power_unit"):
        ec.normalize_metadata({"laser_power": 5})
    with pytest.raises(ValueError, match="out of range"):
        ec.normalize_metadata({"incidence_angle_deg": 90})
    with pytest.raises(ValueError, match="above 0 K"):
        ec.normalize_metadata({"temperature": -300, "temperature_unit": "C"})
    # power is not irradiance unless the spot size is known
    assert ec.normalize_metadata({"laser_power": 1, "laser_power_unit": "mW"})["power_density_mW_per_um2"] is None


def test_excitation_info_stokes_wavelength():
    i = ec.excitation_info(532, 1000, 1000)
    assert i["stokes_wavelength_nm"][0] == pytest.approx(1e7 / (1e7 / 532 - 1000), rel=1e-9)
    assert "recoloured" in i["explanation"]
    with pytest.raises(ValueError):
        ec.excitation_info(532, 0, 30000)


def test_compare_flags_confounding_and_never_invents_data():
    base = {"label": "b", "data_class": "synthetic_example", "metadata": {"excitation_nm": 532, "laser_power": 5, "laser_power_unit": "mW"}, "x": X, "y": Y}
    x2, y2, _ = P.laser_power(X, Y, 2.0, seed=1)
    e = {"label": "e", "data_class": "simulated", "metadata": {"excitation_nm": 633, "laser_power": 10, "laser_power_unit": "mW"}, "x": x2, "y": y2}
    r = ec.compare(base, [e])
    ex = r["experiments"][0]
    assert set(ex["changed_parameters"]) == {"excitation_nm", "laser_power_mW"} and "confounded" in ex["design"]
    assert any("cannot be derived" in w for w in ex["warnings"]) and any("SIMULATED" in w for w in ex["warnings"])
    assert ex["similarity_to_baseline"] > 0.9 and len(ex["difference"]) == len(ex["difference_x"])


# ---- sweeps ------------------------------------------------------------------------------------------------------
def test_sweep_recovers_injected_shift_and_flags_failure():
    s = ws.sweep(X, Y, "paracetamol", "axis_shift", [-20, -4, 0, 4, 20])
    assert all(c["passed"] for c in s["self_checks"])
    by = {r["level"]: r for r in s["rows"]}
    assert by[0]["correct"] and by[4]["correct"] and not by[20]["correct"]
    assert by[20]["truth_score"] < by[4]["truth_score"] < by[0]["truth_score"] + 1e-9
    assert s["first_failure"]["above"]["level"] == 20 and s["data_class"] == "simulated"
    assert "look the same" in s["distinction_note"]


def test_matrix_holds_other_variables_fixed_and_covers_kinds():
    m = ws.experiment_matrix(X, Y, "paracetamol", ["axis_shift", "noise"])
    assert [e["kind"] for e in m["experiments"]] == ["axis_shift", "noise"] and "except" in m["held_constant"]


def test_sweep_rejects_bad_kind_and_too_many_levels():
    with pytest.raises(ValueError):
        ws.sweep(X, Y, None, "nope")
    with pytest.raises(ValueError, match="At most"):
        ws.sweep(X, Y, None, "noise", list(range(30)))


# ---- PCA -------------------------------------------------------------------------------------------------------------
def _ds(n=6, conditions=None, seed=0, **kw):
    return dataset_builder.build_simulated(None, n, 2, conditions, seed, **kw)


def test_pca_outputs_and_metadata_mapping():
    ds = _ds()
    Xp = dataset_builder.preprocess_matrix(ds["raw"])
    r = pa.run_pca(ds["x"], Xp, ds["meta"], 4)
    assert len(r["scores"]) == len(ds["meta"]) and [s["spectrum_id"] for s in r["scores"]] == [m["spectrum_id"] for m in ds["meta"]]
    assert 0 < sum(r["explained_variance_ratio"]) <= 1 + 1e-9 and all(c["passed"] for c in r["self_checks"])
    assert len(r["loadings"][0]["values"]) == len(ds["x"]) and r["loadings"][0]["top_regions"]
    assert r["factor_association"][0]["factor"] == "material"


def test_pca_warns_on_small_or_unlabelled_data():
    ds = dataset_builder.build_simulated(["ethanol"], 3, 1, None, 0)
    r = pa.run_pca(ds["x"], dataset_builder.preprocess_matrix(ds["raw"]), ds["meta"], 2)
    assert any("Only 3 spectra" in w for w in r["warnings"]) and any("Fewer than 2" in w for w in r["warnings"])


def test_align_to_common_grid_validates_ranges():
    a = (np.arange(600, 1600, 2.0), np.ones(500))
    b = (np.arange(1000, 2000, 2.0), np.ones(500))
    grid, M, notes = pa.align_to_common_grid([a, b])
    assert grid[0] == 1000 and grid[-1] <= 1598 and M.shape[0] == 2
    with pytest.raises(ValueError, match="no common"):
        pa.align_to_common_grid([a, (np.arange(2000, 2500, 2.0), np.ones(250))])
    with pytest.raises(ValueError, match="only"):
        pa.align_to_common_grid([a, (np.arange(1590, 2000, 2.0), np.ones(205))])


def test_pca_can_reveal_condition_structure():
    conds = [{"name": "nominal", "steps": []}, {"name": "fluor", "steps": [{"kind": "baseline_distortion", "params": {"amplitude_frac": 3.0}}]}]
    ds = _ds(n=5, conditions=conds)
    # no baseline correction and no normalisation: the acquisition artefact must be visible, not hidden
    Xp = dataset_builder.preprocess_matrix(ds["raw"], {"baseline": False, "smooth": False, "normalize": "none"})
    r = pa.run_pca(ds["x"], Xp, ds["meta"], 5)
    cond = next(a for a in r["factor_association"] if a["factor"] == "condition")
    assert max(cond["eta_squared_per_pc"][:3]) > 0.3


def test_scalers_validated():
    with pytest.raises(ValueError):
        pa.make_scaler("bogus")
    Z = pa.make_scaler("pareto").fit_transform(np.random.default_rng(0).normal(size=(20, 5)))
    assert np.allclose(Z.mean(axis=0), 0, atol=1e-9)


# ---- benchmark / leakage --------------------------------------------------------------------------------------------
def test_split_is_by_specimen_with_no_leakage():
    ds = _ds(n=10)
    (tr, va, te), sets = mb.split_specimens(ds["meta"], 0)
    assert not (sets[0] & sets[1]) and not (sets[0] & sets[2]) and not (sets[1] & sets[2])
    assert len(tr) + len(va) + len(te) == len(ds["meta"])
    for k, ix in enumerate((tr, va, te)):  # repeats of one specimen never straddle splits
        assert {ds["meta"][i]["specimen_id"] for i in ix} == sets[k]


def test_pca_in_predictive_pipeline_is_fitted_on_training_data_only():
    ds = _ds(n=8)
    Xp = dataset_builder.preprocess_matrix(ds["raw"])
    (tr, _, te), _ = mb.split_specimens(ds["meta"], 0)
    p1 = pa.make_pca_pipeline("none", 3).fit(Xp[tr])
    Xmod = Xp.copy()
    Xmod[te] += 100.0  # corrupting test rows must not change anything fitted on train rows
    p2 = pa.make_pca_pipeline("none", 3).fit(Xmod[tr])
    assert np.allclose(p1.named_steps["pca"].components_, p2.named_steps["pca"].components_)


@pytest.fixture(scope="module")
def bench():
    return mb.run_benchmark({"n_specimens": 10, "seed": 3})


def test_benchmark_structure_and_honesty(bench):
    names = {m["model"]: m for m in bench["models"]}
    assert names["cosine_reference"]["status"] == "ran" and names["pca_svm"]["status"] == "ran" and names["pca_logreg"]["status"] == "ran"
    assert names["resnet18_1d"]["status"] == "not run" and names["ramannet"]["status"] == "not implemented"
    assert bench["data_class"] == "simulated" and "NOT a reproduction" in bench["reference_framework"]
    assert "clean (nominal)" in bench["scenarios"] and bench["splits"]["unit_of_independence"] == "specimen"
    rep = names["pca_svm"]["clean_report"]
    assert {"accuracy", "macro_f1", "per_class", "confusion_matrix", "expected_calibration_error"} <= set(rep)
    assert "ml_backend" in bench["environment"]


def test_benchmark_is_reproducible(bench):
    mb._CACHE.clear()
    fresh = mb.run_benchmark({"n_specimens": 10, "seed": 3})
    assert fresh is not bench
    for a, b in zip(fresh["models"], bench["models"]):
        assert a.get("by_scenario") == b.get("by_scenario")


def test_benchmark_insights_do_not_overclaim(bench):
    ins = ig.from_benchmark(bench)
    assert all(i["level"] in LEVELS and i["validation_status"] for i in ins)
    assert any(i["id"] == "bm-deep" and i["level"] == "inconclusive" for i in ins)


@pytest.mark.skipif(not deep_models.torch_available(), reason="PyTorch not installed")
def test_resnet18_1d_architecture():
    import torch
    m = deep_models.build_model("resnet18_1d", 5)
    assert m(torch.zeros(2, 1, 1201)).shape == (2, 5)
    blocks = [mod for mod in m.modules() if mod.__class__.__name__ == "BasicBlock1D"]
    assert len(blocks) == 8  # [2, 2, 2, 2] as in ResNet-18
    assert not any(isinstance(mod, torch.nn.Conv2d) for mod in m.modules())
    assert deep_models.build_model("cnn1d", 5)(torch.zeros(2, 1, 1201)).shape == (2, 5)


@pytest.mark.skipif(not deep_models.torch_available(), reason="PyTorch not installed")
def test_deep_classifier_trains_with_early_stopping():
    ds = _ds(n=8)
    Xp = dataset_builder.preprocess_matrix(ds["raw"])
    y = np.array([ds["materials"].index(m["material"]) for m in ds["meta"]])
    (tr, va, _), _ = mb.split_specimens(ds["meta"], 0)
    clf = deep_models.TorchClassifier("cnn1d", 5, seed=0, epochs=3).fit(Xp[tr], y[tr], Xp[va], y[va])
    assert clf.predict_proba(Xp[va]).shape == (len(va), 5) and clf.epochs_run <= 3 and clf.n_params() > 0


# ---- translation --------------------------------------------------------------------------------------------------
def test_estimate_shift_recovers_known_shift():
    g = np.arange(600, 1600, 1.0)
    ref = np.exp(-((g - 1000) / 8) ** 2) + 0.6 * np.exp(-((g - 1250) / 8) ** 2)
    test = np.interp(g - 6.0, g, ref)  # peaks at +6
    d, _ = st.estimate_shift(g, ref, test)
    assert d == pytest.approx(6.0, abs=0.3)


@pytest.fixture(scope="module")
def tr_res():
    return st.run_controlled_benchmark({"n_specimens": 10})


def test_translation_benchmark_is_labeled_and_beats_baseline_on_position(tr_res):
    assert tr_res["data_class"] == "simulated" and "NOT" in tr_res["warning"]
    assert tr_res["neural_translation"]["status"] == "not run"
    assert all(c["passed"] for c in tr_res["self_checks"])
    base = tr_res["fidelity"]["resample_only"]["aggregate"]
    fixed = tr_res["fidelity"]["shift_correction"]["aggregate"]
    assert fixed["peak_position_error_cm1"]["mean"] < base["peak_position_error_cm1"]["mean"]
    assert fixed["cosine"]["mean"] > base["cosine"]["mean"]
    assert "peak_preservation_rate" in tr_res["comparison_vs_resample_only"]["shift_correction"]


def test_translation_standard_disjoint_from_evaluation(tr_res):
    assert tr_res["calibration_standard"] not in tr_res["labels"]
    assert "disjoint" in tr_res["pairing"]["leakage"]


# ---- insights ---------------------------------------------------------------------------------------------------------
def test_every_insight_has_evidence_fields_and_valid_level():
    s = ws.sweep(X, Y, "paracetamol", "axis_shift", [-12, -4, 0, 4, 12], with_model=True)
    ins = ig.from_sweep(s)
    for i in ins:
        assert i["level"] in LEVELS and i["validation_status"] and i["data_class"] == "simulated" and "evidence" in i
    assert any(i["level"] == "hypothesis" for i in ins)  # calibration-vs-physical ambiguity is a hypothesis, not a finding


def test_failed_self_check_is_reported_in_validation_status():
    assert "FAILED" in ig._validation({"self_checks": [{"name": "x", "passed": False}], "data_class": "simulated"})


# ---- API -------------------------------------------------------------------------------------------------------------------
def test_api_sweep_pca_benchmark_translation_report():
    r = client.post("/api/sensitivity/sweep", json={"spectrum": {"example_id": "demo_paracetamol_synthetic"}, "kind": "axis_shift", "levels": [-8, 0, 8]})
    assert r.status_code == 200 and r.json()["truth"] == "paracetamol" and r.json()["report"]["trust"]
    p = client.post("/api/pca/run", json={"n_specimens": 4, "n_components": 3})
    assert p.status_code == 200 and p.json()["data_class"] == "simulated"
    b = client.post("/api/benchmark/run", json={"n_specimens": 8})
    assert b.status_code == 200
    t = client.post("/api/translation/evaluate", json={"n_specimens": 8})
    assert t.status_code == 200
    studies = [{"kind": "sweep", "title": "S", "result": r.json()}, {"kind": "pca", "title": "P", "result": p.json()},
               {"kind": "benchmark", "title": "B", "result": b.json()}, {"kind": "translation", "title": "T", "result": t.json()}]
    h = client.post("/api/report/research", json=studies)
    assert h.status_code == 200
    for s in ("A. What did we test?", "F. Can we trust this result?", "G. What should the user conclude?", "SIMULATED"):
        assert s in h.text


def test_api_errors_are_explicit():
    assert client.post("/api/sensitivity/sweep", json={"spectrum": {}, "kind": "axis_shift"}).status_code == 422
    assert client.post("/api/sensitivity/sweep", json={"spectrum": {"example_id": "nope"}}).status_code == 404
    assert client.post("/api/sensitivity/sweep", json={"spectrum": {"example_id": "demo_paracetamol_synthetic"}, "kind": "bogus"}).status_code == 422
    assert client.post("/api/pca/run", json={"scaling": "bad"}).status_code == 422
    assert client.post("/api/report/research", json=[]).status_code == 422
    bad = client.post("/api/conditions/compare", json={"baseline": {"label": "a", "spectrum": {"example_id": "demo_ethanol_synthetic"},
                      "metadata": {"laser_power": 5}}, "experiments": [{"label": "b", "simulate": []}]})
    assert bad.status_code == 422 and "unit" in bad.text


def test_api_conditions_simulated_temperature_and_power_update_metadata():
    body = {"baseline": {"label": "25C", "data_class": "synthetic_example", "spectrum": {"example_id": "demo_ethanol_synthetic"},
                         "metadata": {"temperature": 25, "temperature_unit": "C", "laser_power": 10, "laser_power_unit": "mW"}},
            "experiments": [{"label": "hot", "simulate": [{"kind": "temperature", "params": {"delta_T_K": 50, "shift_coeff_cm1_per_K": -0.03}}]},
                            {"label": "2x", "simulate": [{"kind": "laser_power", "params": {"factor": 2}}]}]}
    r = client.post("/api/conditions/compare", json=body).json()
    assert r["data_class"] == "simulated"
    hot, dbl = r["experiments"]
    assert hot["changed_parameters"] == ["temperature_K"] and hot["metadata"]["temperature_K"] == pytest.approx(348.15)
    assert dbl["changed_parameters"] == ["laser_power_mW"] and dbl["metadata"]["laser_power_mW"] == 20
    assert hot["mean_delta_position_cm1"] == pytest.approx(-1.5, abs=1.1)


def test_api_excitation_info_and_perturbation_list():
    assert client.get("/api/conditions/excitation-info?excitation_nm=785").json()["laser_color"] == "near-infrared"
    assert client.get("/api/conditions/excitation-info?excitation_nm=5").status_code == 422
    kinds = {k["kind"] for k in client.get("/api/perturbations").json()}
    assert {"axis_shift", "signal_shift", "axis_warp", "broadening", "temperature", "laser_power"} <= kinds


# ---- scattering relations (units, conventions, Rayleigh scaling) -------------------------------------------------
def test_wavenumber_wavelength_conversion_uses_1e7_nm_per_cm():
    from app.services import scattering as sc
    assert sc.wavenumber_cm1(500.0) == pytest.approx(20000.0)  # 1e7 nm/cm / 500 nm
    assert sc.wavenumber_cm1(532.0) == pytest.approx(18796.99, abs=0.01)
    assert sc.raman_shift_cm1(532.0, 561.8927) == pytest.approx(1000.0, abs=0.001)  # Stokes: positive
    assert sc.raman_shift_cm1(532.0, 505.1272) == pytest.approx(-1000.0, abs=0.01)  # anti-Stokes: negative
    for nm, shift in ((532, 1000), (785, 2900), (633, -500)):
        assert sc.raman_shift_cm1(nm, sc.scattered_wavelength_nm(nm, shift)) == pytest.approx(shift, abs=1e-9)
    with pytest.raises(ValueError):
        sc.scattered_wavelength_nm(532, 20000)


def test_validation_conversion_matches_scattering_module():
    from app.services import scattering as sc
    lam = np.linspace(540, 600, 80)
    s = parse_csv_wl(lam)
    assert s.x == pytest.approx([sc.raman_shift_cm1(532.0, l) for l in lam])
    assert (s.x > 0).all()  # all longer than 532 nm -> Stokes -> positive shifts


def parse_csv_wl(lam):
    from app.services.validation import parse_csv
    body = "wavelength_nm,intensity\n" + "\n".join(f"{l},{10 + i % 7}" for i, l in enumerate(lam))
    return parse_csv(body.encode(), 532.0)


def test_excitation_info_has_stokes_longer_and_anti_stokes_shorter():
    i = ec.excitation_info(532, 500, 1000)
    assert i["stokes_wavelength_nm"][1] == pytest.approx(561.8927, abs=0.001)
    assert i["anti_stokes_wavelength_nm"][1] == pytest.approx(505.1272, abs=0.001)
    assert i["anti_stokes_wavelength_nm"][1] < 532 < i["stokes_wavelength_nm"][0]


def test_anti_stokes_to_stokes_ratio():
    from app.services import scattering as sc
    r = sc.anti_stokes_to_stokes_ratio(1000, 532, 298.15)
    assert r == pytest.approx(0.0123, abs=0.0005)  # (1.1124)^4 * exp(-4.826)
    assert sc.anti_stokes_to_stokes_ratio(1000, 532, 600) > r  # hotter -> relatively stronger anti-Stokes
    assert sc.anti_stokes_to_stokes_ratio(3000, 532, 298.15) < sc.anti_stokes_to_stokes_ratio(500, 532, 298.15)


def test_rayleigh_sphere_formula_scalings_and_limits():
    from app.services import scattering as sc
    f = lambda **k: sc.rayleigh_sphere_intensity(**{"i0": 1, "diameter": 20, "n_rel": 1.5, "wavelength": 532, "distance": 1e6, "theta_rad": np.pi / 2, **k})
    assert f(wavelength=266) / f(wavelength=532) == pytest.approx(16)  # lambda^-4
    assert f(diameter=40) / f(diameter=20) == pytest.approx(64)  # d^6
    assert f(distance=2e6) / f(distance=1e6) == pytest.approx(0.25)  # R^-2
    assert f(theta_rad=0) / f(theta_rad=np.pi / 2) == pytest.approx(2)  # (1+cos^2)/(2): forward = 2x side
    assert f(n_rel=1.0) == 0  # no index contrast, no scattering
    with pytest.raises(ValueError, match="diameter"):
        f(diameter=200)


def test_report_svgs_have_axis_labels_and_peak_annotations():
    r = client.post("/api/analyze/example/demo_paracetamol_synthetic").json()
    html = client.post("/api/report", json=r).text
    assert "Raman shift (cm⁻¹)" in html and "Intensity (as supplied)" in html and "Processed intensity (a.u.)" in html
    assert f">{r['peaks'][0]['position']:.0f}</text>" in html  # peak position label
