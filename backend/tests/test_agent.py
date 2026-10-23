"""LangGraph workflow and the fact-checked plain-language explanation. No network: the LLM is always faked."""
import copy
import json
from types import SimpleNamespace

import pytest

from app.agent import graph, llm
from app.services import explanation, orchestrator, pipeline

EX = pipeline.DATA_DIR / "examples"
SYNTH = {"category": "synthetic", "description": "x", "source": "synthetic", "license": "x"}


def build(name="paracetamol", **kw):
    raw = (EX / f"demo_{name}_synthetic.csv").read_bytes()
    return orchestrator.build(raw, f"demo_{name}_synthetic", provenance=SYNTH, origin="synthetic", **kw)


@pytest.fixture(scope="module")
def ok_report():
    return build("paracetamol", use_agent=False)


@pytest.fixture(scope="module")
def inconclusive_report():
    return build("noisy", use_agent=False)


def good_draft(report):
    """What a well-behaved model would return: the rule-based text re-worded, citing real evidence."""
    e = explanation.rule_based(report)
    return {k: e[k] for k in ("headline", "what_we_found", "how_sure", "what_this_does_not_mean", "next_steps")}


def test_rule_based_text_passes_its_own_fact_check(ok_report, inconclusive_report):
    for r in (ok_report, inconclusive_report):
        e = explanation.rule_based(r)
        assert explanation.verify(e, e["evidence"], r) == []
        assert all(f["evidence"] for f in e["what_we_found"])
    assert "could not" in explanation.rule_based(inconclusive_report)["headline"]


def test_fact_check_rejects_invented_numbers_materials_and_overclaims(ok_report, inconclusive_report):
    ev = explanation.evidence(ok_report)
    d = good_draft(ok_report)
    d["what_we_found"].append({"text": "The match is 97.3% certain.", "evidence": [ev[0]["id"]]})
    assert any("97.3" in p for p in explanation.verify(d, ev, ok_report))
    d = good_draft(ok_report)
    d["what_we_found"][0]["text"] += " It also resembles beta carotene."
    assert any("Beta Carotene" in p for p in explanation.verify(d, ev, ok_report))
    d = good_draft(ok_report)
    d["what_we_found"][0]["evidence"] = ["E99"]
    assert any("E99" in p for p in explanation.verify(d, ev, ok_report))
    d = good_draft(ok_report)
    d["how_sure"] = "It is safe to eat."
    assert any("scope" in p for p in explanation.verify(d, ev, ok_report))
    ev_i = explanation.evidence(inconclusive_report)
    d = good_draft(inconclusive_report)
    d["headline"] = "Your sample is polypropylene."
    probs = explanation.verify(d, ev_i, inconclusive_report)
    assert any("headline" in p for p in probs)


def test_evidence_pack_holds_no_raw_data(ok_report):
    msg = llm.prompt(explanation.evidence(ok_report))
    assert len(msg) < 4000
    assert str(ok_report["sections"]["spectrum"]["data"]["raw"][5]) not in msg


def stream(monkeypatch, drafts, configured=True):
    calls = []

    def fake_write(ev, problems=None, client=None):
        calls.append(problems)
        d = drafts[min(len(calls) - 1, len(drafts) - 1)]
        if isinstance(d, Exception):
            raise d
        return d

    monkeypatch.setattr(llm, "configured", lambda: configured)
    monkeypatch.setattr(llm, "write", fake_write)
    raw = (EX / "demo_paracetamol_synthetic.csv").read_bytes()
    evs = list(orchestrator.run(raw, "demo_paracetamol_synthetic", provenance=SYNTH, origin="synthetic"))
    return evs, calls


def test_graph_streams_every_stage_in_order_and_accepts_a_checked_draft(monkeypatch, ok_report):
    evs, calls = stream(monkeypatch, [good_draft(ok_report)])
    stages = [e for e in evs if e["event"] == "stage"]
    assert [e["stage"] for e in stages if e["status"] == "running"] == [s for s, _ in orchestrator.STAGES]
    assert [e["completed"] for e in stages if e["status"] != "running"] == list(range(1, len(orchestrator.STAGES) + 1))
    e = evs[-1]["report"]["explanation"]
    assert e["source"] == "llm_verified" and e["attempts"] == 1 and len(calls) == 1
    assert explanation.NOT_DIAGNOSTIC in e["what_this_does_not_mean"]


def test_graph_retries_with_the_fact_checker_feedback_then_accepts(monkeypatch, ok_report):
    bad = good_draft(ok_report)
    bad["headline"] = "Your sample is 99.9% paracetamol."
    evs, calls = stream(monkeypatch, [bad, good_draft(ok_report)])
    e = evs[-1]["report"]["explanation"]
    assert e["source"] == "llm_verified" and e["attempts"] == 2
    assert calls[0] is None and any("99.9" in p for p in calls[1])


def test_graph_falls_back_to_the_standard_summary(monkeypatch, ok_report):
    bad = good_draft(ok_report)
    bad["headline"] = "Your sample is 99.9% paracetamol."
    evs, calls = stream(monkeypatch, [bad])
    e = evs[-1]["report"]["explanation"]
    assert e["source"] == "rule_based" and "fact check" in e["llm_status"] and len(calls) == graph.MAX_ATTEMPTS
    evs, _ = stream(monkeypatch, [llm.LLMUnavailable("Claude API error 529.")])
    assert evs[-1]["report"]["explanation"]["llm_status"] == "Claude API error 529."
    evs, calls = stream(monkeypatch, [good_draft(ok_report)], configured=False)
    assert evs[-1]["report"]["explanation"]["source"] == "rule_based" and calls == []


def test_graph_and_linear_runner_produce_the_same_report(monkeypatch):
    monkeypatch.setattr(llm, "configured", lambda: False)
    a, b = build(use_agent=False), build()
    for r in (a, b):
        r.pop("generated_at")
        r["analysis"].pop("timestamp")
        r["brief"].pop("report_id")
        r["explanation"].pop("llm_status", None)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_graph_stops_on_an_unreadable_file():
    evs = list(orchestrator.run(b"not a spectrum\n", "x"))
    assert evs[-1]["event"] == "error" and evs[-1]["stage"] == "validate"
    assert not any(e["event"] == "result" for e in evs)


def test_claude_request_shape(ok_report, monkeypatch):
    """The call sends only evidence, asks for schema-constrained JSON and never sends sampling parameters."""
    seen = {}
    draft = good_draft(ok_report)

    class Msgs:
        def create(self, **kw):
            seen.update(kw)
            return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(draft))])

    client = SimpleNamespace(beta=SimpleNamespace(messages=Msgs()))
    monkeypatch.delenv("RAMAN_LLM_MODEL", raising=False)
    out = llm.write(explanation.evidence(ok_report), None, client)
    assert out == draft
    assert seen["model"] == llm.DEFAULT_MODEL and "temperature" not in seen
    assert seen["output_config"]["format"]["schema"] == llm.SCHEMA
    assert seen["messages"][0]["content"].startswith("Evidence facts:")
    refusal = SimpleNamespace(stop_reason="refusal", content=[])
    client.beta.messages.create = lambda **kw: refusal
    with pytest.raises(llm.LLMUnavailable):
        llm.write(explanation.evidence(ok_report), None, client)


def test_llm_is_off_without_a_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert not llm.configured()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("RAMAN_LLM", "off")
    assert not llm.configured()


def test_html_report_leads_with_the_plain_answer(ok_report):
    from app.services import report_html
    html = report_html.build(copy.deepcopy(ok_report))
    assert html.index(ok_report["explanation"]["headline"]) < html.index("Technical appendix")
