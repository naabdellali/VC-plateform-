"""
Mistral provider support - added after Gemini's free tier proved too
unreliable in production for this workload: gemini-2.5-flash was retired for
new users within months of being chosen, and its replacement
(gemini-3.6-flash) turned out to cap free-tier usage at 20 requests/DAY -
too low for even a single deck upload's ~20-25 sequential LLM calls (see
test_llm_client_gemini.py and llm_client.py's _GEMINI_RETRYABLE_CODES comment
for that history). Mistral's free "Experiment" plan publishes a much higher
ceiling (1 req/sec, 500K tokens/minute, 1B tokens/month at the time this was
added), so it's now the PREFERRED provider (checked first in
LlmClient.__init__), with Gemini and Anthropic kept as fallbacks.

Same three things must hold as for Gemini:
1. Mistral is preferred when multiple keys are configured.
2. A 429 is retried with backoff, not treated as fatal on the first attempt.
3. A call that still fails after retries degrades _call_json/reason to a
   clearly-labelled failure result instead of crashing the whole upload
   request (the "ne fais pas semblant" precedent - see
   test_llm_client_salvage.py).
"""
from unittest import mock

import pytest

from app.services.llm_client import LlmClient, LlmResult
import app.services.llm_client as llm_client_module


class _FakeMistralError(Exception):
    """Stand-in for mistralai.client.errors.MistralError - the real one
    requires a live httpx.Response to construct (status_code is derived from
    it), which isn't needed to test our retry logic. Mirrors
    test_llm_client_gemini.py's _FakeAPIError pattern."""
    def __init__(self, status_code, message="rate limited"):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


def test_mistral_is_preferred_over_gemini_and_anthropic(monkeypatch):
    monkeypatch.setattr(llm_client_module.settings, "mistral_api_key", "fake-mistral-key")
    monkeypatch.setattr(llm_client_module.settings, "gemini_api_key", "fake-gemini-key")
    monkeypatch.setattr(llm_client_module.settings, "anthropic_api_key", "fake-anthropic-key")
    with mock.patch("mistralai.client.Mistral") as MockMistral:
        client = LlmClient()
        assert client._provider == "mistral"
        assert client.mode == "live"
        MockMistral.assert_called_once_with(api_key="fake-mistral-key")


def test_gemini_used_when_only_gemini_and_anthropic_configured(monkeypatch):
    # Unchanged fallback behaviour - an analyst with no Mistral key yet
    # should still get Gemini rather than nothing.
    monkeypatch.setattr(llm_client_module.settings, "mistral_api_key", None)
    monkeypatch.setattr(llm_client_module.settings, "gemini_api_key", "fake-gemini-key")
    monkeypatch.setattr(llm_client_module.settings, "anthropic_api_key", "fake-anthropic-key")
    with mock.patch("google.genai.Client") as MockClient:
        client = LlmClient()
        assert client._provider == "gemini"
        MockClient.assert_called_once_with(api_key="fake-gemini-key")


def _client_with_fake_mistral():
    client = LlmClient()
    client._provider = "mistral"
    client._client = mock.Mock()
    return client


def _mistral_response(text):
    resp = mock.Mock()
    resp.choices = [mock.Mock(message=mock.Mock(content=text))]
    return resp


def test_mistral_retries_on_429_and_eventually_succeeds(monkeypatch):
    monkeypatch.setattr(llm_client_module, "_MISTRAL_MIN_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(llm_client_module, "_last_mistral_call_at", 0.0)
    monkeypatch.setattr(llm_client_module.time, "sleep", lambda *_: None)

    client = _client_with_fake_mistral()
    good_resp = _mistral_response("the real answer")
    client._client.chat.complete.side_effect = [_FakeMistralError(429), _FakeMistralError(429), good_resp]

    with mock.patch("mistralai.client.errors.MistralError", _FakeMistralError):
        text = client._call("system", "user", 500)

    assert text == "the real answer"
    assert client._client.chat.complete.call_count == 3


def test_mistral_raises_after_exhausting_retries(monkeypatch):
    monkeypatch.setattr(llm_client_module, "_MISTRAL_MIN_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(llm_client_module, "_last_mistral_call_at", 0.0)
    monkeypatch.setattr(llm_client_module.time, "sleep", lambda *_: None)

    client = _client_with_fake_mistral()
    client._client.chat.complete.side_effect = _FakeMistralError(429)

    with mock.patch("mistralai.client.errors.MistralError", _FakeMistralError):
        with pytest.raises(_FakeMistralError):
            client._call("system", "user", 500)


def test_mistral_does_not_retry_non_rate_limit_errors(monkeypatch):
    monkeypatch.setattr(llm_client_module, "_MISTRAL_MIN_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(llm_client_module, "_last_mistral_call_at", 0.0)
    monkeypatch.setattr(llm_client_module.time, "sleep", lambda *_: None)

    client = _client_with_fake_mistral()
    client._client.chat.complete.side_effect = _FakeMistralError(500, "internal error")

    with mock.patch("mistralai.client.errors.MistralError", _FakeMistralError):
        with pytest.raises(_FakeMistralError):
            client._call("system", "user", 500)
    assert client._client.chat.complete.call_count == 1


def test_call_json_degrades_gracefully_when_mistral_call_fails_persistently(monkeypatch):
    llm = LlmClient()
    llm._client = object()  # force mode == "live" without a real provider client
    llm._provider = "mistral"
    monkeypatch.setattr(llm, "_call", mock.Mock(side_effect=RuntimeError("quota exhausted")))

    result = llm._call_json("system prompt", "user prompt")

    assert isinstance(result, LlmResult)
    assert result.parsed is None
    assert "LIVE CALL FAILED" in result.text
    assert "quota exhausted" in result.text
