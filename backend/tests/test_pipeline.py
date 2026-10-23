import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import matching, pipeline, preprocessing
from app.services.validation import ValidationError, parse_csv

client = TestClient(app)


def csv_bytes(x, y, header="raman_shift_cm1,intensity"):
    return (header + "\n" + "\n".join(f"{a},{b}" for a, b in zip(x, y))).encode()


def test_missing_columns():
    with pytest.raises(ValidationError, match="Missing required"):
        parse_csv(b"a,b\n1,2\n")


def test_too_few_points_and_nonnumeric():
    with pytest.raises(ValidationError, match="at least"):
        parse_csv(csv_bytes(range(10), range(10)))
    with pytest.raises(ValidationError, match="non-numeric"):
        parse_csv(b"raman_shift_cm1,intensity\n" + b"1,2\n" * 60 + b"x,3\n")


def test_duplicates_nan_constant_and_empty():
    x = list(range(60))
    with pytest.raises(ValidationError, match="Duplicate"):
        parse_csv(csv_bytes(x[:-1] + [0], np.arange(60) % 7))
    with pytest.raises(ValidationError, match="constant"):
        parse_csv(csv_bytes(x, [5] * 60))
    with pytest.raises(ValidationError, match="NaN"):
        parse_csv(csv_bytes(x, ["nan"] + list(range(59))))
    with pytest.raises(ValidationError, match="empty"):
        parse_csv(b"")


def test_wavelength_requires_excitation():
    x = np.linspace(540, 600, 80)
    raw = csv_bytes(x, np.arange(80) % 9, "wavelength_nm,intensity")
    with pytest.raises(ValidationError, match="excitation"):
        parse_csv(raw)
    s = parse_csv(raw, 532)
    assert s.x[0] > 0 and any("Converted" in w for w in s.warnings)


def test_unsorted_is_sorted_with_warning():
    x = np.arange(60.0)[::-1]
    s = parse_csv(csv_bytes(x, np.arange(60) % 7 + 1))
    assert s.x[0] == 0 and s.warnings


def test_savgol_window_clamped_and_poly_rejected():
    y = np.random.default_rng(0).normal(size=60)
    out, _, p = preprocessing.preprocess(y, window=500, poly=3, normalize="none")
    assert p["savgol_window"] <= 60 and out.shape == y.shape
    with pytest.raises(ValueError):
        preprocessing.preprocess(y, window=3, poly=5)


def test_cosine_zero_vector_and_no_overlap():
    assert matching.cosine(np.zeros(5), np.ones(5)) == 0.0
    m = matching.compare(np.arange(100.0, 200), np.ones(100), [{"id": "r", "name": "r", "x": np.arange(500.0, 600), "y": np.ones(100)}])
    assert m[0]["coverage"] == 0.0


def test_paracetamol_example_matches_and_is_reproducible():
    r1 = client.post("/api/analyze/example/demo_paracetamol_synthetic").json()
    r2 = client.post("/api/analyze/example/demo_paracetamol_synthetic").json()
    assert r1["status"] == "ok" and r1["top_matches"][0]["reference_id"] == "paracetamol"
    assert r1["processed"] == r2["processed"] and r1["matches"] == r2["matches"]
    assert r1["is_diagnostic"] is False


def test_ethanol_example_matches():
    r = client.post("/api/analyze/example/demo_ethanol_synthetic").json()
    assert r["top_matches"][0]["reference_id"] == "ethanol"


def test_noisy_and_narrow_are_inconclusive():
    for s in ("demo_noisy_synthetic", "demo_narrow_range_synthetic"):
        r = client.post(f"/api/analyze/example/{s}").json()
        assert r["status"] == "inconclusive" and r["top_matches"] == [] and r["quality_warnings"]


def test_api_errors_and_report():
    assert client.get("/health").status_code == 200
    assert len(client.get("/api/examples").json()) == 4
    assert client.post("/api/analyze", files={"file": ("a.csv", b"foo\n1\n")}).status_code == 422
    assert client.post("/api/analyze/example/nope").status_code == 404
    assert client.post("/api/analyze", files={"file": ("a.csv", b"x")}, data={"window": "2"}).status_code == 422
    r = client.post("/api/analyze/example/demo_paracetamol_synthetic").json()
    html = client.post("/api/report", json=r).text
    assert "NON-DIAGNOSTIC" in html and "Limitations" in html
    assert client.post("/api/report", json={}).status_code == 422


# ---- regression tests: SNR, metadata, invalid values, coverage, inconclusive, provenance ----
from app.services import quality  # noqa: E402
from app.services.validation import Spectrum  # noqa: E402


def _synthetic_spectrum(noise, seed=1):
    x = np.arange(600, 3001, 2.0)
    y = 500 + 1000 / (1 + ((x - 1500) / 8) ** 2) + np.random.default_rng(seed).normal(0, noise, x.size)
    return x, y


def test_snr_not_artificial_when_smoothing_disabled():
    """Regression: smooth=False used to give noise=0 -> snr=1e9."""
    x, y = _synthetic_spectrum(20)
    r = pipeline.analyze(Spectrum(x, y), options={"smooth": False})
    assert r["snr"] is not None and 1 < r["snr"] < 1e4
    r2 = pipeline.analyze(Spectrum(x, y), options={"smooth": True})
    assert abs(r["snr"] - r2["snr"]) < 1e-9  # SNR is independent of the smoothing choice


def test_snr_tracks_noise_level_and_noiseless_is_undefined_not_huge():
    assert quality.estimate_snr(_synthetic_spectrum(5)[1]) > quality.estimate_snr(_synthetic_spectrum(200)[1])
    assert quality.estimate_snr(np.linspace(0, 1, 100)) is None  # zero noise estimate -> undefined
    status, reasons = quality.assess(None, [], [])
    assert status == "inconclusive" and any("could not be estimated" in r for r in reasons)


def test_inconclusive_when_smoothing_off_and_noisy_via_api():
    r = client.post("/api/analyze/example/demo_noisy_synthetic", json={"smooth": False}).json()
    assert r["status"] == "inconclusive" and r["snr"] < 1e4 and r["top_matches"] == []


def test_missing_excitation_is_metadata_not_calibration():
    csv = csv_bytes(np.arange(600, 1000, 4.0), 100 + 50 / (1 + ((np.arange(600, 1000, 4.0) - 800) / 6) ** 2) + np.arange(100) % 3)
    r = client.post("/api/analyze", files={"file": ("a.csv", csv)}).json()
    m = r["metadata"]
    assert m["excitation_nm"] is None and m["excitation_source"] == "not provided"
    assert m["calibration_status"] == "not_verified" and m["wavelength_converted_to_raman_shift"] is False
    assert any("Excitation wavelength not provided" in w for w in r["quality_warnings"])


def test_declared_excitation_never_verifies_calibration():
    r = client.post("/api/analyze/example/demo_paracetamol_synthetic").json()
    assert r["metadata"]["excitation_source"] == "user-declared" and r["metadata"]["calibration_status"] == "not_verified"
    x = np.linspace(540, 600, 80)
    raw = csv_bytes(x, 10 + 40 / (1 + ((x - 570) / 2) ** 2) + np.arange(80) % 5, "wavelength_nm,intensity")
    r = client.post("/api/analyze", files={"file": ("w.csv", raw)}, data={"excitation_nm": "532"}).json()
    assert r["metadata"]["wavelength_converted_to_raman_shift"] is True and r["metadata"]["calibration_status"] == "not_verified"
    assert client.post("/api/analyze", files={"file": ("w.csv", raw)}).status_code == 422  # no excitation -> reject


def test_invalid_values_rejected():
    x = list(range(60))
    with pytest.raises(ValidationError, match="NaN or infinite"):
        parse_csv(csv_bytes(x, ["inf"] + list(range(59))))
    with pytest.raises(ValidationError, match="positive"):  # non-positive wavelengths cannot be converted
        parse_csv(csv_bytes(np.linspace(-5, 5, 80), np.arange(80) % 7, "wavelength_nm,intensity"), 532)
    for bad in ({"normalize": "bogus"}, {"window": 1}, {"als_p": 2}):
        assert client.post("/api/analyze/example/demo_paracetamol_synthetic", json=bad).status_code == 422
    assert client.post("/api/analyze", files={"file": ("a.csv", b"raman_shift_cm1,intensity\n" + b"1,2\n" * 60)}).status_code == 422


def test_poor_coverage_is_inconclusive_with_reason():
    r = client.post("/api/analyze/example/demo_narrow_range_synthetic").json()
    assert r["status"] == "inconclusive"
    assert any("Insufficient overlap" in w for w in r["quality_warnings"])
    assert max(m["coverage"] for m in r["matches"]) < quality.MIN_COVERAGE


def test_provenance_visible_in_api_and_report():
    r = client.post("/api/analyze/example/demo_paracetamol_synthetic").json()
    assert r["data_provenance"]["sample"]["category"] == "synthetic" and r["data_provenance"]["references_all_synthetic"] is True
    assert any("SYNTHETIC" in w for w in r["quality_warnings"])
    html = client.post("/api/report", json=r).text
    assert "SYNTHETIC DATA" in html and "not_verified" in html and "provisional" in html.lower()
    up = client.post("/api/analyze", files={"file": ("u.csv", open(pipeline.DATA_DIR / "examples/demo_ethanol_synthetic.csv", "rb"))}).json()
    assert up["data_provenance"]["sample"]["category"] == "user_supplied"  # uploads are never labelled as synthetic or validated


def test_scores_never_described_as_probabilities_of_identification():
    r = client.post("/api/analyze/example/demo_paracetamol_synthetic").json()
    assert "not probabilities of identification" in r["similarity_note"]
    assert "provisional" in r["quality_thresholds"]["status"]  # SNR/coverage stay provisional even once scores are calibrated
    assert all("not the probability of identification" in m["explanation"] for m in r["matches"] if m["overlap"])
    assert r["is_diagnostic"] is False
