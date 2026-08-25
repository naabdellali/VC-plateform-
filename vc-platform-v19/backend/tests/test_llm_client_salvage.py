"""
Regression coverage for the deck-extraction bug: a dense deck's claims array
can get cut off mid-object when the model hits its own output token limit,
and a plain json.loads() on that then fails entirely. Previously that meant
the caller got parsed=None, which every category-filtering caller
(extraction.parsed if isinstance(extraction.parsed, list) else []) turns
into "zero claims extracted" - exactly the analyst-reported bug of dense
decks reading as if nothing was extracted.

_salvage_json_array is the fix: recover every complete top-level object from
a truncated array response instead of discarding the whole batch.
"""
from app.services.llm_client import _salvage_json_array, LlmClient, LlmResult


def test_salvage_recovers_complete_objects_from_truncated_array():
    truncated = (
        '[{"category": "market_size", "claim": "TAM 64bn", "value": "64000000000", "slide_reference": 5}, '
        '{"category": "traction_metric", "claim": "35 clients", "value": "35", "slide_reference": 3}, '
        '{"category": "team_background", "claim": "CEO named Jane D'  # cut off mid-string, no closing brace
    )
    result = _salvage_json_array(truncated)
    assert result is not None
    assert len(result) == 2
    assert result[0]["category"] == "market_size"
    assert result[1]["category"] == "traction_metric"


def test_salvage_handles_braces_inside_quoted_strings():
    # A claim value containing literal braces (e.g. pasted from a template) must not
    # desynchronize the brace-depth tracking used to find object boundaries.
    text = '[{"category": "other", "claim": "revenue formula {x+y}", "value": null, "slide_reference": null}]'
    result = _salvage_json_array(text)
    assert result is not None
    assert len(result) == 1
    assert result[0]["claim"] == "revenue formula {x+y}"


def test_salvage_returns_none_for_non_array_text():
    assert _salvage_json_array('{"not": "an array"}') is None
    assert _salvage_json_array("not json at all") is None


def test_salvage_returns_none_when_nothing_recoverable():
    assert _salvage_json_array('[{"broken') is None


def test_call_json_falls_back_to_salvage_on_truncated_array_response(monkeypatch):
    llm = LlmClient()
    llm._client = object()  # force mode == "live" without a real Anthropic client
    truncated_raw = (
        '[{"category": "market_size", "claim": "TAM 64bn", "value": "64000000000", "slide_reference": 5}, '
        '{"category": "traction_metric", "claim": "35 clients", "value": "35", "slide_reference": 3}, '
        '{"category": "team_background", "claim": "CEO named Jane D'
    )
    monkeypatch.setattr(llm, "_call", lambda system, user, max_tokens=2000: truncated_raw)

    result = llm._call_json("system prompt", "user prompt")
    assert isinstance(result, LlmResult)
    assert result.parsed is not None
    assert len(result.parsed) == 2
    assert {c["category"] for c in result.parsed} == {"market_size", "traction_metric"}


def test_call_json_still_returns_none_for_truncated_non_array_response(monkeypatch):
    # A truncated dict-shaped response (most LLM calls return a dict, not an array)
    # has nothing for the array-salvage path to recover - must stay None, not crash.
    llm = LlmClient()
    llm._client = object()
    monkeypatch.setattr(llm, "_call", lambda system, user, max_tokens=2000: '{"tam": "64bn", "sam": "1.5')

    result = llm._call_json("system prompt", "user prompt")
    assert result.parsed is None
