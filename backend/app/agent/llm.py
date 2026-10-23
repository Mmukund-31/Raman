"""Claude call that rewrites the evidence pack as a plain-language explanation.

Only the numbered evidence facts are sent: never the uploaded file, the spectrum arrays or user metadata.
Configuration (environment):
  ANTHROPIC_API_KEY      enables the call (without it the rule-based summary is used)
  RAMAN_LLM_MODEL        model id, default claude-opus-5-5
  RAMAN_LLM              set to "off" to disable the call even when a key is present
  RAMAN_LLM_TIMEOUT_S    per-request timeout in seconds, default 30
"""
import json
import os

DEFAULT_MODEL = "claude-opus-5-5"

SYSTEM = """You explain the result of a Raman spectroscopy analysis to someone with no science background.

You receive numbered evidence facts (E1, E2, ...) computed by the analysis software. Rules:
- Use only those facts. Do not add knowledge about the material, its uses, its safety or its value.
- Every finding must cite the ids of the facts it is based on.
- Copy numbers exactly as they appear in the facts; do not compute new ones.
- Name only materials that appear in the facts.
- If the verdict is inconclusive, the headline must say plainly that the sample could not be identified, and nothing
  may suggest that it was.
- If the closest reference is an idealised literature-band reference (category synthetic), report it neutrally as the closest reference match and add one short clause recommending confirmation against a measured reference. Do not call it a demo.
- Plain words, short sentences, reading age about 12. Explain any unavoidable term in passing.
- Make no medical, legal, safety or authenticity claims."""

SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string", "description": "One sentence answer to 'what is my sample?'"},
        "what_we_found": {"type": "array", "items": {
            "type": "object",
            "properties": {"text": {"type": "string"}, "evidence": {"type": "array", "items": {"type": "string"}}},
            "required": ["text", "evidence"], "additionalProperties": False}},
        "how_sure": {"type": "string", "description": "How confident the result is and why, in two or three sentences."},
        "what_this_does_not_mean": {"type": "array", "items": {"type": "string"}},
        "next_steps": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["headline", "what_we_found", "how_sure", "what_this_does_not_mean", "next_steps"],
    "additionalProperties": False,
}


class LLMUnavailable(Exception):
    pass


def configured() -> bool:
    return os.getenv("RAMAN_LLM", "").lower() != "off" and bool(os.getenv("ANTHROPIC_API_KEY"))


def model_id() -> str:
    return os.getenv("RAMAN_LLM_MODEL", DEFAULT_MODEL)


def prompt(evidence: list[dict], problems: list[str] | None = None) -> str:
    facts = "\n".join(f"{e['id']} [{e['label']}]: {e['text']}" for e in evidence)
    msg = f"Evidence facts:\n{facts}\n\nWrite the explanation."
    if problems:
        msg += ("\n\nA previous draft was rejected by the fact checker for these reasons; fix all of them:\n- "
                + "\n- ".join(problems))
    return msg


def write(evidence: list[dict], problems: list[str] | None = None, client=None) -> dict:
    """Returns the parsed explanation dict. Raises LLMUnavailable on any API problem or refusal."""
    import anthropic

    client = client or anthropic.Anthropic(timeout=float(os.getenv("RAMAN_LLM_TIMEOUT_S", "30")), max_retries=1)
    try:
        resp = client.beta.messages.create(
            model=model_id(),
            max_tokens=4000,
            system=SYSTEM,
            messages=[{"role": "user", "content": prompt(evidence, problems)}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.APIConnectionError as e:
        raise LLMUnavailable(f"Could not reach the Claude API: {e}")
    except anthropic.RateLimitError:
        raise LLMUnavailable("The Claude API rate limit was reached.")
    except anthropic.APIStatusError as e:
        raise LLMUnavailable(f"Claude API error {e.status_code}.")
    if resp.stop_reason == "refusal":
        raise LLMUnavailable("The model declined to write the explanation.")
    if resp.stop_reason == "max_tokens":
        raise LLMUnavailable("The explanation was cut off.")
    text = next((b.text for b in resp.content if b.type == "text"), None)
    try:
        return json.loads(text)
    except (TypeError, json.JSONDecodeError):
        raise LLMUnavailable("The model did not return valid JSON.")
