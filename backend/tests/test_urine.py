import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import urine
from app.services.pipeline import read_xy

client = TestClient(app)
EX = urine.URINE_DIR / "examples"


def _example(name):
    return read_xy(EX / f"{name}.csv")


def test_band_height_measures_peak_above_local_line():
    x = np.arange(400, 1801, 2.0)
    y = 0.001 * x + 2.0 * np.exp(-(((x - 1124) / 5) ** 2))  # sloping background must not count as signal
    assert urine.band_height(x, y, 1124) == pytest.approx(2.0, rel=0.02)
    assert urine.band_height(x, y, 700) < 0.02


def test_indices_are_dilution_independent():
    x, y = _example("urine_glycosuria_synthetic")
    a = urine.indices(x, urine.process(y))
    b = urine.indices(x, urine.process(2.5 * y))
    assert a["glucose"] == pytest.approx(b["glucose"], rel=0.02)


def test_trial_study_shape_and_grouped_cross_validation():
    s = urine.study("trial")
    assert s["dataset"]["category"] == "synthetic" and s["positive_group"] == "diabetes"
    assert [g["id"] for g in s["groups"]] == ["control", "diabetes"]
    c = s["classification"]
    assert c["n"] == 70  # one baseline spectrum per participant
    assert sum(c["confusion"].values()) == 70 and 0 <= c["auc"] <= 1
    assert len(s["pca"]["explained_variance_ratio"]) == 3 and sum(s["pca"]["explained_variance_ratio"]) <= 1
    assert len(s["grid"]) == len(s["mean_spectra"][0]["mean"]) == len(s["pca"]["loadings"][0])


def test_trial_tracks_glucose_and_responders_fall():
    t = urine.study("trial")["trial"]
    assert t["weeks"] == [0, 4, 8, 12]
    assert t["calibration"]["r"] > 0.9
    means = {m["cohort"]: m["mean"] for m in t["cohort_means"]}
    assert means["responder"][-1] < 0.5 * means["responder"][0]
    assert means["non-responder"][-1] > 0.7 * means["non-responder"][0]
    assert len(t["responder_surface"]["z"]) == 4


@pytest.mark.parametrize("name,flag", [("urine_healthy_synthetic", None), ("urine_glycosuria_synthetic", "glycosuria"),
                                       ("urine_ketonuria_synthetic", "ketonuria"), ("urine_week12_responder_synthetic", None)])
def test_examples_are_placed_and_flagged(name, flag):
    x, y = _example(name)
    r = urine.analyze(x, y, "trial")
    text = " ".join(r["flags"])
    if flag:
        assert flag in text and r["nearest_group"] == "diabetes"
    else:
        assert "glycosuria" not in text and r["nearest_group"] == "control"
    assert "not" in r["disclaimer"]


def test_analyze_rejects_narrow_range():
    x = np.arange(1000, 1400, 2.0)
    with pytest.raises(ValueError, match="620–1700"):
        urine.analyze(x, np.ones_like(x), "trial")


def test_routes():
    assert {d["dataset_id"] for d in client.get("/api/urine/datasets").json()} >= {"trial"}
    assert client.get("/api/urine/study/nope").status_code == 422
    r = client.get("/api/urine/study/trial")
    assert r.status_code == 200 and r.json()["trial"]["weeks"] == [0, 4, 8, 12]
    ex = client.get("/api/urine/examples").json()
    assert len(ex) == 4
    assert client.get(f"/api/urine/examples/{ex[0]['sample_id']}/download").status_code == 200
    assert client.get("/api/urine/examples/..%2Fmanifest/download").status_code == 404
    r = client.post("/api/urine/analyze", data={"example": "urine_glycosuria_synthetic", "dataset": "trial"})
    assert r.status_code == 200 and r.json()["nearest_group"] == "diabetes"
    with open(EX / "urine_healthy_synthetic.csv", "rb") as f:
        r = client.post("/api/urine/analyze", files={"file": ("u.csv", f, "text/csv")}, data={"dataset": "trial"})
    assert r.status_code == 200 and r.json()["sample_name"] == "u"
    assert client.post("/api/urine/analyze", data={"dataset": "trial"}).status_code == 422


@pytest.mark.skipif(not (urine.URINE_DIR / "zenodo" / "spectra.csv").exists(), reason="measured dataset not downloaded")
def test_measured_dataset():
    s = urine.study("zenodo")
    assert s["dataset"]["category"] == "measured" and s["dataset"]["license"] == "CC BY 1.0"
    assert {g["id"] for g in s["groups"]} == {"healthy", "non_diabetic_ckd", "diabetic"}
    assert s["trial"] is None and 0 <= s["classification"]["auc"] <= 1


def test_reference_change_grows_with_level():
    r = urine.reference_change("trial")["glucose"]
    assert r["n_people"] == 30 and r["sd_within"] > 0 and r["cv_assumed"] == urine.ASSUMED_CV["glucose"]
    assert urine.rcv_at(r, 0) == pytest.approx(r["rcv_at_zero"], abs=1e-4)
    assert urine.rcv_at(r, 1.5) > 5 * urine.rcv_at(r, 0)


def test_personal_profiles_separate_responders_from_non_responders():
    people = urine.study("trial")["trial"]["participants"]
    for p in people:
        g = urine.participant(p["participant"])["indices"]["glucose"]
        fell = g["significant"] and g["change"] < 0
        assert fell == (p["response"] == "responder"), p["participant"]
    r = urine.participant(next(p["participant"] for p in people if p["response"] == "responder"))
    assert r["weeks"] == [0, 4, 8, 12] and len(r["spectra"]) == 4 and len(r["pc_path"]) == 4
    assert len(r["spectra"][0]) == len(r["grid"]) == len(r["difference"])
    assert any("own baseline" in t for t in r["insights"])


def test_participant_route():
    assert client.get("/api/urine/participant/C01").json()["arm"] == "control"
    assert client.get("/api/urine/participant/NOPE").status_code == 404
    assert client.get("/api/urine/participant/C01?dataset=bad").status_code == 422
