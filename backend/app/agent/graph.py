"""The analysis workflow as a LangGraph state graph.

    validate -> process -> conditions -> sensitivity -> pca -> models -> report -> explain_write -> explain_verify
       |           |                                                                    ^              |
       +-> END     +-> END   (fatal input/processing errors stop the run)                +-- retry once -+--> fallback
                                                                                                    accept -> END

Every analysis node calls the same stage function as the linear runner (services.orchestrator.STAGE_FUNCS), so the
science is identical either way. The graph adds the routing: stop on a fatal error, and draft -> fact-check -> retry
or fall back for the plain-language explanation. Progress events go out through LangGraph's custom stream, in the
same NDJSON format the frontend already reads.
"""
import functools
from typing import Any, TypedDict

from ..services import explanation, orchestrator as orch
from . import llm

MAX_ATTEMPTS = 2


def available() -> bool:
    try:
        import langgraph  # noqa: F401
    except ImportError:
        return False
    return True


class State(TypedDict, total=False):
    ctx: Any            # orchestrator.Run: the shared analysis context (not serialised; no checkpointer is used)
    failed: bool
    draft: dict | None
    problems: list
    attempts: int
    llm_error: str | None


def _writer():
    from langgraph.config import get_stream_writer
    return get_stream_writer()


def _stage_node(sid):
    def node(state: State):
        c, w = state["ctx"], _writer()
        w(orch.stage_event(c, sid))
        try:
            status, detail = orch.STAGE_FUNCS[sid](c)
        except orch.AnalysisFailed as e:
            w({"event": "error", "stage": e.stage, "message": str(e)})
            return {"failed": True}
        w(orch.stage_event(c, sid, status, detail))
        return {"failed": False}
    node.__name__ = f"stage_{sid}"
    return node


def explain_write(state: State):
    c, w = state["ctx"], _writer()
    attempts = state.get("attempts", 0)
    if attempts == 0:
        w(orch.stage_event(c, "explain"))
    if not llm.configured():
        return {"draft": None, "llm_error": "not configured (set ANTHROPIC_API_KEY to enable)", "attempts": attempts + 1}
    ev = explanation.evidence(c.report)
    try:
        draft = llm.write(ev, state.get("problems") or None)
    except llm.LLMUnavailable as e:
        return {"draft": None, "llm_error": str(e), "attempts": attempts + 1}
    return {"draft": draft, "llm_error": None, "attempts": attempts + 1}


def explain_verify(state: State):
    c = state["ctx"]
    draft = state.get("draft")
    if draft is None:
        return {"problems": []}
    problems = explanation.verify(draft, explanation.evidence(c.report), c.report)
    if not problems:
        ev = explanation.evidence(c.report)
        c.report["explanation"] = {
            "source": "llm_verified", "headline": draft["headline"], "what_we_found": draft["what_we_found"],
            "how_sure": draft["how_sure"], "what_this_does_not_mean": draft["what_this_does_not_mean"] + [explanation.NOT_DIAGNOSTIC],
            "next_steps": draft["next_steps"], "glossary": explanation.GLOSSARY, "evidence": ev, "model": llm.model_id(),
            "attempts": state["attempts"],
            "note": ("Written by an AI model from the numbered facts only, then checked automatically: every number and "
                     "material name was matched against the computed results before it was shown."),
        }
        _writer()(orch.stage_event(c, "explain", "done", f"AI-written, fact-checked ({llm.model_id()})"))
    return {"problems": problems}


def _after_verify(state: State):
    if state.get("draft") is None:
        return "fallback"
    if not state.get("problems"):
        return "accept"
    return "retry" if state["attempts"] < MAX_ATTEMPTS else "fallback"


def fallback(state: State):
    c = state["ctx"]
    e = explanation.rule_based(c.report)
    reason = state.get("llm_error") or ("the AI draft failed the fact check: " + "; ".join(state.get("problems", [])[:3]))
    e["llm_status"] = reason
    c.report["explanation"] = e
    _writer()(orch.stage_event(c, "explain", "done", "standard summary"))
    return {}


def _continue(state: State):
    return "stop" if state.get("failed") else "next"


@functools.lru_cache(maxsize=1)
def workflow():
    from langgraph.graph import END, START, StateGraph

    g = StateGraph(State)
    analysis = [sid for sid, _ in orch.STAGES if sid != "explain"]
    for sid in analysis:
        g.add_node(sid, _stage_node(sid))
    g.add_node("explain_write", explain_write)
    g.add_node("explain_verify", explain_verify)
    g.add_node("fallback", fallback)
    g.add_edge(START, analysis[0])
    for a, b in zip(analysis, analysis[1:] + ["explain_write"]):
        if a in ("validate", "process", "report"):  # stages that can fail fatally
            g.add_conditional_edges(a, _continue, {"next": b, "stop": END})
        else:
            g.add_edge(a, b)
    g.add_edge("explain_write", "explain_verify")
    g.add_conditional_edges("explain_verify", _after_verify, {"accept": END, "retry": "explain_write", "fallback": "fallback"})
    g.add_edge("fallback", END)
    return g.compile()


def run(c):
    """Streams the same events as orchestrator.run_linear()."""
    failed = False
    for ev in workflow().stream({"ctx": c, "attempts": 0}, stream_mode="custom"):
        failed = failed or ev.get("event") == "error"
        yield ev
    if not failed:
        yield {"event": "result", "report": c.report}
