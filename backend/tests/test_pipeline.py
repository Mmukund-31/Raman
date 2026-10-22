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
