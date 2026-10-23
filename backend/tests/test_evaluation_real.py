"""Curated measured library and its held-out evaluation."""
import json

import pytest

from app.services import evaluation_real as er, pipeline, quality

REAL = pipeline.DATA_DIR / "references_real"
HAVE = (REAL / "manifest.json").exists()


def q(truth, top1, score, margin, other=False):
    return {"truth": truth, "top1": top1, "score": score, "margin": margin, "other_blocking": other, "rank": 1 if top1 == truth else 2}


def test_calibration_meets_the_false_match_target():
    pos = [q("a", "a", 0.95, 0.2)] * 40 + [q("a", "b", 0.7, 0.01)] * 10 + [q("a", "a", 0.8, 0.1)] * 10
    neg = [q("a", "b", 0.75, 0.05)] * 20 + [q("a", "b", 0.9, 0.01)] * 5
    t = er.calibrate(pos, neg, target=0.05)
    acc = [x for x in pos if er._accept(x, t)]
    wrong = sum(x["top1"] != x["truth"] for x in acc) + sum(er._accept(x, t) for x in neg)
    assert wrong / (len(acc) + sum(er._accept(x, t) for x in neg)) <= 0.05
    assert sum(x["top1"] == x["truth"] for x in acc) == 50  # keeps every correct answer that is separable
    s = er.summarise(pos, t)
    assert s["accuracy_when_answered"] == 1.0 and s["answered_fraction"] == pytest.approx(50 / 60, abs=1e-3)


@pytest.mark.skipif(not HAVE, reason="measured library not curated")
def test_curated_library_meets_its_own_criteria():
    m = json.loads((REAL / "manifest.json").read_text(encoding="utf-8"))
    by = {}
    for r in m:
        assert r["category"] == "measured" and r["license"] and r["citation"] and r["source_id"]
        assert r["range_cm1"][0] <= 300 and r["range_cm1"][1] >= 1100 and r["snr"] >= 20
        assert (REAL / r["file"]).exists()
        by.setdefault(r["material"], set()).add(r["source_id"])
    assert all(len(v) >= 2 for v in by.values()), "every material needs two independent specimens"


@pytest.mark.skipif(not HAVE, reason="measured library not curated")
def test_held_out_query_never_sees_its_own_spectrum():
    refs = pipeline.load_references("measured")
    r = refs[0]
    res = er._query(r, {r["id"]}, [], 0)
    a = pipeline.analyze(pipeline.Spectrum(r["x"], r["y"]), "q", "t", None, {"library": "measured"}, {"category": "measured"},
                         frozenset({r["id"]}))
    assert all(m["reference_id"] != r["id"] for m in a["matches"])
    assert res["truth"] == r["material"]
    neg = er._query(r, {x["id"] for x in refs if x["material"] == r["material"]}, [], 0)
    assert neg["rank"] is None  # the material is absent from the negative-control library


@pytest.mark.skipif(not (REAL / "evaluation.json").exists(), reason="evaluation not run")
def test_published_evaluation_and_thresholds_are_consistent():
    ev = er.load()
    assert "rows" not in ev
    t = ev["thresholds"]
    assert t["achieved_false_match_rate"] is None or t["achieved_false_match_rate"] <= t["target_false_match_rate"]
    assert quality.MIN_SCORE == ev["thresholds"]["min_score"]
    assert "calibrated" in quality.THRESHOLD_STATUS
    assert er.headline(ev).startswith("In a held-out test")
