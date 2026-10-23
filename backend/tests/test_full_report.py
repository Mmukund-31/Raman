"""Unified workflow: one upload -> streamed stages -> one report containing only analyses the data supports."""
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import orchestrator, pipeline, report_html

client = TestClient(app)
EX = pipeline.DATA_DIR / "examples"
SECTIONS = ["validation", "spectrum", "peaks", "matching", "conditions", "sensitivity", "pca", "benchmark", "translation", "quality"]


def ex_bytes(name="paracetamol"):
    return (EX / f"demo_{name}_synthetic.csv").read_bytes()


def events_of(resp):
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/x-ndjson")
    return [json.loads(line) for line in resp.text.splitlines() if line.strip()]


def post_full(files, data=None):
    return client.post("/api/full-report", files=files, data=data or {})


@pytest.fixture(scope="module")
def single():
    return events_of(post_full({"file": ("sample.csv", ex_bytes(), "text/csv")}, {"sample_id": "sample", "excitation_nm": "785"}))


def test_stream_reports_every_stage_in_order_with_genuine_completion(single):
    stages = [e for e in single if e["event"] == "stage"]
    ids = [s for s, _ in orchestrator.STAGES]
    assert [e["stage"] for e in stages if e["status"] == "running"] == ids
    # each stage starts, then finishes, before the next one starts
    for i, sid in enumerate(ids):
        assert stages[2 * i]["stage"] == stages[2 * i + 1]["stage"] == sid
        assert stages[2 * i]["status"] == "running" and stages[2 * i + 1]["status"] in ("done", "skipped", "error")
        assert stages[2 * i + 1]["completed"] == i + 1 and stages[2 * i]["completed"] == i
    assert all(e["total"] == len(ids) for e in stages)
    assert single[-1]["event"] == "result"


def test_single_spectrum_report_marks_unsupported_analyses_without_fabricating(single):
    r = single[-1]["report"]
    s = r["sections"]
    assert list(s) == SECTIONS
    for k in ("validation", "spectrum", "peaks", "matching", "sensitivity", "quality"):
        assert s[k]["status"] == "complete", k
    assert s["conditions"]["status"] == "partial"
    assert "comparison" not in s["conditions"]["data"]
    for k in ("pca", "benchmark", "translation"):
        assert s[k]["status"] == "insufficient_data"
        assert s[k]["reason"] and s[k]["requirements"]
        assert not any(key in s[k]["data"] for key in ("scores", "models", "fidelity", "explained_variance_ratio"))
    assert {a["id"]: a["status"] for a in r["executive_summary"]["availability"]}["pca"] == "insufficient_data"
    assert r["is_diagnostic"] is False
    assert s["quality"]["data"]["conclusive"] is False


def test_report_reuses_existing_calculations_unchanged(single):
    r = single[-1]["report"]
    direct = client.post("/api/analyze", files={"file": ("sample.csv", ex_bytes(), "text/csv")},
                         data={"sample_id": "sample", "excitation_nm": "785", "baseline": "true", "smooth": "true"}).json()
    assert [m["score"] for m in r["sections"]["matching"]["data"]["matches"]] == [m["score"] for m in direct["matches"]]
    assert [p["position"] for p in r["sections"]["spectrum"]["data"]["peaks"]] == [p["position"] for p in direct["peaks"]]
    assert r["sections"]["spectrum"]["data"]["processed"] == pytest.approx(direct["processed"])
    assert r["analysis"]["status"] == direct["status"]


def test_metadata_is_flagged_when_missing_and_converted_when_given(single):
    c = single[-1]["report"]["sections"]["conditions"]["data"]
    assert c["recorded"] == {"excitation_nm": 785.0}
    assert "temperature_K" in c["missing"] and "laser_power_mW" in c["missing"]
    assert c["excitation"]["laser_color"] == "near-infrared"
    r = orchestrator.build(ex_bytes(), metadata={"temperature": 25, "temperature_unit": "C", "laser_power": 0.5,
                                                  "laser_power_unit": "W"})
    rec = r["sections"]["conditions"]["data"]["recorded"]
    assert rec["temperature_K"] == pytest.approx(298.15) and rec["laser_power_mW"] == pytest.approx(500)


def test_sensitivity_section_is_simulated_and_summarises_ranking_stability(single):
    s = single[-1]["report"]["sections"]["sensitivity"]
    assert s["data_class"] == "simulated"
    rows = [r for r in s["data"]["rows"] if "error" not in r]
    assert all("raw" not in r and "x" not in r for r in rows)  # trimmed for transport
    base = s["data"]["baseline"]["top1"]
    stable = s["data"]["stable_within_cm1"]
    assert all(r["top1"] == base for r in rows if abs(r["level"]) <= stable)
    if s["data"]["top1_changed_at"]:
        assert abs(s["data"]["top1_changed_at"][0]) > stable


def test_additional_spectra_enable_pca_and_condition_comparison():
    files = [("file", ("main.csv", ex_bytes(), "text/csv")),
             ("extra_files", ("ethanol.csv", ex_bytes("ethanol"), "text/csv")),
             ("extra_files", ("noisy.csv", ex_bytes("noisy"), "text/csv")),
             ("extra_files", ("broken.csv", b"a,b\n1,2\n", "text/csv"))]
    r = client.post("/api/full-report", files=files, data={"stream": "false", "primary_label": "A",
                                                          "extra_labels": json.dumps(["B", "B", "C"])}).json()
    s = r["sections"]
    assert s["pca"]["status"] == "partial"  # 3 spectra < MIN_SPECTRA_WARN: ran, flagged as unstable
    assert s["pca"]["data"]["n_spectra"] == 3
    assert {p["material"] for p in s["pca"]["data"]["scores"]} == {"A", "B"}
    assert s["conditions"]["status"] == "complete" and len(s["conditions"]["data"]["comparison"]["experiments"]) == 2
    assert s["validation"]["status"] == "partial"
    assert s["validation"]["data"]["rejected_additional_spectra"][0]["name"] == "broken"
    assert s["benchmark"]["status"] == "insufficient_data"  # 3 spectra are not a labelled benchmark dataset


def test_invalid_csv_streams_an_error_and_stops():
    ev = events_of(post_full({"file": ("bad.csv", b"x,y\n1,2\n", "text/csv")}))
    assert ev[-1]["event"] == "error" and ev[-1]["stage"] == "validate"
    assert "at least 50" in ev[-1]["message"]  # 'x,y' headers are accepted now; one data row is still too few
    assert not any(e["event"] == "result" for e in ev)
    r = post_full({"file": ("bad.csv", b"x,y\n1,2\n", "text/csv")}, {"stream": "false"})
    assert r.status_code == 422


def test_invalid_metadata_and_form_inputs_are_rejected():
    ev = events_of(post_full({"file": ("s.csv", ex_bytes(), "text/csv")}, {"metadata": json.dumps({"laser_power": 5})}))
    assert ev[-1]["event"] == "error" and "laser_power_unit" in ev[-1]["message"]
    assert post_full({"file": ("s.csv", ex_bytes(), "text/csv")}, {"metadata": "{not json"}).status_code == 422
    assert post_full({"file": ("s.csv", ex_bytes(), "text/csv")}, {"window": "2"}).status_code == 422


def test_declared_origin_is_preserved_in_provenance():
    r = orchestrator.build(ex_bytes(), origin="synthetic")
    assert r["data_provenance"]["sample"]["category"] == "synthetic"
    assert any("SYNTHETIC" in w for w in r["sections"]["quality"]["data"]["warnings"])
    r = orchestrator.build(ex_bytes(), origin="measured")
    assert r["data_provenance"]["sample"]["declared_origin"] == "measured"
    assert r["declared_origin"] == "measured"


def test_example_endpoint_labels_synthetic_data_and_known_truth():
    r = client.post("/api/full-report/example/demo_noisy_synthetic?stream=false").json()
    # the bundled-example truth rule (shared with the research labs) only knows ids named after a reference
    assert r["inputs"]["truth_label"] is None
    r2 = client.post("/api/full-report/example/demo_ethanol_synthetic?stream=false").json()
    assert r2["inputs"]["truth_label"] == "ethanol"
    assert r["data_provenance"]["sample"]["category"] == "synthetic"
    assert r["analysis"]["status"] == "inconclusive"
    assert "inconclusive" in r["sections"]["matching"]["summary"].lower()
    assert client.post("/api/full-report/example/nope?stream=false").status_code == 404


def test_optional_stage_failure_does_not_sink_the_report(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("simulated failure")
    monkeypatch.setattr(orchestrator.ws, "sweep", boom)
    ev = list(orchestrator.run(ex_bytes()))
    assert any(e["event"] == "stage" and e["stage"] == "sensitivity" and e["status"] == "error" for e in ev)
    r = ev[-1]["report"]
    assert r["sections"]["sensitivity"]["status"] == "error" and "simulated failure" in r["sections"]["sensitivity"]["reason"]
    assert r["sections"]["quality"]["status"] == "complete"


def test_clean_makes_output_json_safe():
    out = orchestrator.clean({"a": float("nan"), "b": [np.float64(1.5), np.int64(2), np.bool_(True)], "c": np.array([np.inf])})
    assert out == {"a": None, "b": [1.5, 2, True], "c": [None]}
    json.dumps(out, allow_nan=False)


def test_html_report_is_a_concise_brief(single):
    r = single[-1]["report"]
    resp = client.post("/api/full-report/html", json=r)
    assert resp.status_code == 200
    html = resp.text
    for h in ("Sample information", "Result summary", "Candidate ranking", "Quality control", "Interpretation", "Recommendations",
              "Technical appendix", "Principal peaks", "Method notes and limitations", "Methods"):
        assert h in html
    assert html.index("Result summary") < html.index("Technical appendix")  # the summary page comes first
    assert r["explanation"]["headline"] in html and r["brief"]["report_id"] in html
    assert html.count("<svg") == 3  # letterhead logo, the overlay figure and the technical spectrum
    assert "Not performed:" in html and "requires a labelled training dataset" in html
    assert "not a probability" in html.lower() and "synthetic" in html.lower()
    assert "<svg" in html and "@media print" in html
    assert len(html) < 60_000  # a brief, not a data dump
    assert client.post("/api/full-report/html", json={"x": 1}).status_code == 422


def test_brief_is_short_and_derived_from_computed_sections(single):
    r = single[-1]["report"]
    b = r["brief"]
    assert len(b["findings"]) <= 3 and len(b["limitations"]) <= 3 and len(b["recommendations"]) <= 3
    assert len(b["peaks"]) <= 8 and len(b["references"]) <= 3 and len(b["metrics"]) == 4
    assert b["references"][0]["score"] == r["sections"]["matching"]["data"]["matches"][0]["score"]
    assert b["metrics"][0]["value"] == str(len(r["sections"]["spectrum"]["data"]["peaks"]))
    assert {x["title"] for x in b["not_performed"]} == {"PCA", "Model benchmark", "Spectral translation"}
    assert b["match_claimed"] == (r["analysis"]["status"] == "ok")


def test_brief_never_claims_a_match_when_inconclusive():
    r = client.post("/api/full-report/example/demo_noisy_synthetic?stream=false").json()
    b = r["brief"]
    assert b["verdict"] == "Inconclusive" and not b["match_claimed"]
    assert "No reliable match" in b["headline"]
    assert any("likely noise" in f for f in b["findings"])
    assert "signal-to-noise" in b["limitations"][0].lower()
    html = report_html.build(r)
    assert "No confident match" in html and "Confirmed match" not in html and "Probable match" not in html


def test_html_report_escapes_user_text():
    r = orchestrator.build(ex_bytes(), sample_id="<script>alert(1)</script>")
    html = report_html.build(r)
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html


def test_omitted_boolean_options_keep_their_defaults():
    r = client.post("/api/full-report", files={"file": ("s.csv", ex_bytes(), "text/csv")}, data={"stream": "false"}).json()
    assert r["inputs"]["options"]["baseline"] is True and r["inputs"]["options"]["smooth"] is True
    r = client.post("/api/full-report", files={"file": ("s.csv", ex_bytes(), "text/csv")},
                    data={"stream": "false", "baseline": "false"}).json()
    assert r["inputs"]["options"]["baseline"] is False
    assert post_full({"file": ("s.csv", ex_bytes(), "text/csv")}, {"smooth": "maybe"}).status_code == 422


def test_candidate_ranking_reports_the_score_it_is_ordered_by(single):
    items = single[-1]["report"]["visual"]["candidates"]["items"]
    ranks = [c["rank_score"] for c in items]
    assert ranks == sorted(ranks, reverse=True)
    assert all(0 <= c["coverage"] <= 1 and c["rank_score"] <= c["score"] + 1e-9 for c in items)
    html = client.post("/api/full-report/html", json=single[-1]["report"]).text
    assert all(h in html for h in ("Ranking score", "Coverage", "Similarity"))
