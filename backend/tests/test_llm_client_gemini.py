"""
Gemini provider support - added when the analyst's Anthropic account ran out of
API credit and she chose the free Google AI Studio tier over paying, accepting
the tradeoff that Google's free tier may use submitted deck content to improve
its models (see .env.example). Three things must hold for this to actually work
rather than just compile:

1. Provider selection prefers Gemini when both keys are configured (an analyst
   who's out of Anthropic credit but has a Gemini key should get the free
   provider, not an immediate 400 from Anthropic on every call).
2. The free tier's 10 req/min limit is respected with pacing + retry-with-backoff
   on 429 - a single dense-deck upload makes ~20+ sequential LLM calls, so without
   this, every real upload would fail almost immediately.
3. A call that still fails after retries (quota fully exhausted, network error)
   degrades _call_json/reason to a clearly-labelled failure result instead of
   raising and crashing the whole upload request - see the Phase 1 "ne fais pas
   semblant" precedent (test_llm_client_salvage.py) for why a failure must never
   silently read as "the platform found nothing" without a visible marker.
"""
from unittest import mock

import pytest

from app.services.llm_client import LlmClient, LlmResult
import app.services.llm_client as llm_client_module


class _FakeAPIError(Exception):
    """Stand-in for google.genai.errors.APIError - real one requires a live
    response object to construct, which isn't needed to test our retry logic."""
    def __init__(self, code, message="rate limited"):
        self.code = code
        self.message = message
        super().__init__(message)


def test_gemini_is_preferred_when_both_keys_are_configured(monkeypatch):
    monkeypatch.setattr(llm_client_module.settings, "gemini_api_key", "fake-gemini-key")
    monkeypatch.setattr(llm_client_module.settings, "anthropic_api_key", "fake-anthropic-key")
    with mock.patch("google.genai.Client") as MockClient:
        client = LlmClient()
        assert client._provider == "gemini"
        assert client.mode == "live"
        MockClient.assert_called_once_with(api_key="fake-gemini-key")


def test_anthropic_used_when_only_anthropic_key_configured(monkeypatch):
    monkeypatch.setattr(llm_client_module.settings, "gemini_api_key", None)
    monkeypatch.setattr(llm_client_module.settings, "anthropic_api_key", "fake-anthropic-key")
    with mock.patch("anthropic.Anthropic") as MockAnthropic:
        client = LlmClient()
        assert client._provider == "anthropic"
        MockAnthropic.assert_called_once_with(api_key="fake-anthropic-key")


def test_no_keys_configured_stays_in_mock_mode(monkeypatch):
    monkeypatch.setattr(llm_client_module.settings, "gemini_api_key", None)
    monkeypatch.setattr(llm_client_module.settings, "anthropic_api_key", None)
    client = LlmClient()
    assert client._provider is None
    assert client.mode == "mock"


def _client_with_fake_gemini():
    """A live-mode LlmClient with a mocked google-genai client, bypassing the
    real constructor - mirrors test_llm_client_salvage.py's `llm._client =
    object()` pattern, but keeps a real Mock so call args can be asserted."""
    client = LlmClient()
    client._provider = "gemini"
    client._client = mock.Mock()
    return client


def test_gemini_retries_on_429_and_eventually_succeeds(monkeypatch):
    monkeypatch.setattr(llm_client_module, "_GEMINI_MIN_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(llm_client_module, "_last_gemini_call_at", 0.0)
    monkeypatch.setattr(llm_client_module.time, "sleep", lambda *_: None)

    client = _client_with_fake_gemini()
    good_resp = mock.Mock(text="the real answer")
    client._client.models.generate_content.side_effect = [_FakeAPIError(429), _FakeAPIError(429), good_resp]

    with mock.patch("google.genai.errors.APIError", _FakeAPIError):
        text = client._call("system", "user", 500)

    assert text == "the real answer"
    assert client._client.models.generate_content.call_count == 3


def test_gemini_raises_after_exhausting_retries(monkeypatch):
    monkeypatch.setattr(llm_client_module, "_GEMINI_MIN_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(llm_client_module, "_last_gemini_call_at", 0.0)
    monkeypatch.setattr(llm_client_module.time, "sleep", lambda *_: None)

    client = _client_with_fake_gemini()
    client._client.models.generate_content.side_effect = _FakeAPIError(429)

    with mock.patch("google.genai.errors.APIError", _FakeAPIError):
        with pytest.raises(_FakeAPIError):
            client._call("system", "user", 500)


def test_gemini_does_not_retry_non_rate_limit_errors(monkeypatch):
    # A 500 or auth error should fail fast, not burn through the retry budget
    # pointlessly waiting on an error retrying can't fix.
    monkeypatch.setattr(llm_client_module, "_GEMINI_MIN_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(llm_client_module, "_last_gemini_call_at", 0.0)
    monkeypatch.setattr(llm_client_module.time, "sleep", lambda *_: None)

    client = _client_with_fake_gemini()
    client._client.models.generate_content.side_effect = _FakeAPIError(500, "internal error")

    with mock.patch("google.genai.errors.APIError", _FakeAPIError):
        with pytest.raises(_FakeAPIError):
            client._call("system", "user", 500)
    assert client._client.models.generate_content.call_count == 1


def test_call_json_degrades_gracefully_when_live_call_fails_persistently(monkeypatch):
    # Exactly the scenario that caused the analyst's "Failed to fetch" with
    # Anthropic (credit exhausted -> unhandled exception -> crashed request).
    # A persistent Gemini failure (quota exhausted after retries) must not
    # repeat that failure mode.
    llm = LlmClient()
    llm._client = object()  # force mode == "live" without a real provider client
    monkeypatch.setattr(llm, "_call", mock.Mock(side_effect=RuntimeError("quota exhausted")))

    result = llm._call_json("system prompt", "user prompt")

    assert isinstance(result, LlmResult)
    assert result.parsed is None
    assert "LIVE CALL FAILED" in result.text
    assert "quota exhausted" in result.text


def test_reason_degrades_gracefully_when_live_call_fails_persistently(monkeypatch):
    llm = LlmClient()
    llm._client = object()
    monkeypatch.setattr(llm, "_call", mock.Mock(side_effect=RuntimeError("quota exhausted")))

    result = llm.reason("system", "user")

    assert result.parsed is None
    assert "LIVE CALL FAILED" in result.text
