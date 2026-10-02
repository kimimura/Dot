import pytest

import config
from core import ai
from core.ai import errors, pacing

MESSAGES = [
    ("429 RESOURCE_EXHAUSTED: quota exceeded for metric generate_requests_per_model_per_day, limit PerDay", errors.DAILY),
    ("503 UNAVAILABLE. The model is overloaded.", errors.BUSY),
    ("400 INVALID_ARGUMENT: API key not valid. Please pass a valid API key.", "service credentials rejected"),
    ("403 PERMISSION_DENIED", "request refused (permission denied)"),
    ("404 NOT_FOUND: models/gemini-9 is not found", "service misconfigured"),
]


@pytest.mark.parametrize("raw, shown", MESSAGES)
def test_errors_are_translated_into_plain_messages(raw, shown):
    assert errors.friendly(Exception(raw)) == shown


@pytest.mark.parametrize("shown", [s for _, s in MESSAGES] + [errors.BUSY, errors.DAILY, errors.GARBLED])
def test_messages_never_name_the_provider_or_speak_as_dot(shown):
    low = shown.lower()
    assert "gemini" not in low and "google" not in low and "model" not in low
    assert not low.startswith("i ") and "i've" not in low and " my " not in f" {low} "


def test_the_wait_time_is_read_from_a_rate_limit_reply():
    assert pacing.retry_after("Please retry in 17.5s.") == 17.5
    assert pacing.retry_after("{'retryDelay': '23s'}") == 23.0
    assert pacing.retry_after("no hint here") is None


def test_requests_are_spaced_to_the_per_minute_limit(monkeypatch):
    clock = {"t": 1000.0}
    slept = []
    monkeypatch.setattr(pacing.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(pacing.time, "sleep", lambda s: (slept.append(s), clock.__setitem__("t", clock["t"] + s)))
    monkeypatch.setattr(config, "AI_RPM", 3)
    monkeypatch.setattr(pacing, "_sent", pacing.deque())
    for _ in range(3):
        pacing.wait_turn()
    assert slept == []
    clock["t"] += 10
    pacing.wait_turn()
    assert slept and 49 < sum(slept) < 51


def test_without_a_key_reading_still_works_offline(monkeypatch):
    monkeypatch.setattr(config, "AI_PROVIDER", "")
    monkeypatch.setattr(config, "AI_KEY", "")
    assert ai.status() == "offline" and isinstance(ai.get_llm(), ai.OfflineAdapter)
