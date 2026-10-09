from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import config
from core import activity, ai
from core.ai import errors, gemini, pacing
from core.ai.errors import Truncated
from core.ai.gemini import GeminiAdapter

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


@pytest.mark.parametrize("shown", [s for _, s in MESSAGES] + [errors.BUSY, errors.DAILY, errors.GARBLED, errors.CUT_OFF])
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


class Models:
    def __init__(self, reply, finish=""):
        self.reply, self.finish, self.caps = reply, finish, []

    def generate_content(self, model, contents, config):
        self.caps.append(config.max_output_tokens)
        self.tool_calling_off = config.automatic_function_calling and config.automatic_function_calling.disable
        return SimpleNamespace(text=self.reply, candidates=[SimpleNamespace(finish_reason=self.finish)])


def reader_with(models, names=("model",)):
    reader = GeminiAdapter("key", names)
    reader.client = SimpleNamespace(models=models)
    return reader


def google(code, status, message, quota=""):
    # an error laid out the way the service's library prints one
    details = f", 'details': [{{'violations': [{{'quotaId': '{quota}'}}]}}]" if quota else ""
    return f"{code} {status}. {{'error': {{'code': {code}, 'message': {message!r}, 'status': '{status}'{details}}}}}"


PER_DAY = google(429, "RESOURCE_EXHAUSTED", "You exceeded your current quota.", "GenerateRequestsPerDayPerProjectPerModel-FreeTier")
PER_MINUTE = google(429, "RESOURCE_EXHAUSTED", "You exceeded your current quota. Please retry in 30s.", "GenerateRequestsPerMinutePerProjectPerModel-FreeTier")


class Rationed:
    # each model answers until the reply list given for it says to refuse
    def __init__(self, refusals):
        self.refusals, self.asked = refusals, []

    def generate_content(self, model, contents, config):
        self.asked.append(model)
        if model in self.refusals:
            raise Exception(self.refusals[model])
        return SimpleNamespace(text=f'{{"by": "{model}"}}', candidates=[SimpleNamespace(finish_reason="STOP")])


@pytest.fixture
def quiet(monkeypatch):
    lines = []
    monkeypatch.setattr(pacing, "wait_turn", lambda: None)
    monkeypatch.setattr(activity, "note", lines.append)
    return lines


def test_a_model_used_up_for_the_day_hands_over_to_the_next_and_rests(quiet):
    models = Rationed({"m1": PER_DAY})
    reader = reader_with(models, ["m1", "m2", "m3"])
    assert reader.complete(b"%PDF", "hello") == {"by": "m2"}
    assert reader.complete(b"%PDF", "hello again") == {"by": "m2"}
    assert models.asked == ["m1", "m2", "m2"]
    assert quiet == ["m1: 429 RESOURCE_EXHAUSTED: You exceeded your current quota. — switching to m2"]


OVERLOADED = google(503, "UNAVAILABLE", "This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.")


@pytest.fixture
def slept(monkeypatch):
    waits = []
    monkeypatch.setattr(gemini.time, "sleep", waits.append)
    return waits


class Recovers(Rationed):
    # refuses the first few asks, then answers
    def __init__(self, refusal, times):
        super().__init__({})
        self.refusal, self.times = refusal, times

    def generate_content(self, model, contents, config):
        if len(self.asked) < self.times:
            self.asked.append(model)
            raise Exception(self.refusal)
        return super().generate_content(model, contents, config)


@pytest.mark.parametrize("refusal, said", [
    (OVERLOADED, "503 UNAVAILABLE: This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later."),
    (PER_MINUTE, "429 RESOURCE_EXHAUSTED: You exceeded your current quota. Please retry in 30s."),
    (google(500, "INTERNAL", "An internal error has occurred."), "500 INTERNAL: An internal error has occurred.")])
def test_a_busy_model_is_waited_for_instead_of_handing_over_and_its_own_words_are_shown(quiet, slept, refusal, said):
    models = Recovers(refusal, 1)
    assert reader_with(models, ["m1", "m2"]).complete(b"%PDF", "hello") == {"by": "m1"}
    assert models.asked == ["m1", "m1"] and slept == [120] and quiet == [f"m1: {said} — trying again in 2 min"]


def test_a_model_still_busy_on_the_second_try_is_given_up_on(quiet, slept):
    models = Rationed({"m1": OVERLOADED})
    with pytest.raises(errors.LLMError, match="busy right now"):
        reader_with(models, ["m1", "m2"]).complete(b"%PDF", "hello")
    assert models.asked == ["m1", "m1"] and slept == [120]
    assert quiet[-1].startswith("m1: 503 UNAVAILABLE: This model is currently") and quiet[-1].endswith("— tried 2 times, giving up")


def test_a_longer_wait_asked_for_by_the_limit_is_kept(quiet, slept):
    reader_with(Recovers(google(429, "RESOURCE_EXHAUSTED", "Please retry in 300s."), 1), ["m1"]).complete(b"%PDF", "hello")
    assert slept == [300] and quiet == ["m1: 429 RESOURCE_EXHAUSTED: Please retry in 300s. — trying again in 5 min"]


def test_an_error_not_laid_out_as_usual_is_still_shown_whole(quiet):
    with pytest.raises(errors.LLMError):
        reader_with(Rationed({"m1": "Connection reset by peer"}), ["m1"]).complete(b"%PDF", "hello")
    assert quiet == ["m1: Connection reset by peer — stopped"]


def test_the_library_does_not_retry_quietly_on_its_own():
    reader = GeminiAdapter("key", ["m1"])
    assert reader.client._api_client._http_options.retry_options.attempts == 1


def test_when_every_model_is_used_up_for_the_day_the_error_is_plain(quiet):
    reader = reader_with(Rationed({"m1": PER_DAY, "m2": PER_DAY}), ["m1", "m2"])
    with pytest.raises(errors.LLMError, match="daily limit reached"):
        reader.complete(b"%PDF", "hello")
    assert quiet[-1] == "m2: 429 RESOURCE_EXHAUSTED: You exceeded your current quota. — no other model left"


def test_no_model_set_says_so_and_there_is_no_built_in_default(monkeypatch):
    monkeypatch.delenv("LLM_MODELS", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    assert [m.strip() for m in config.env("LLM_MODELS", "LLM_MODEL", "GEMINI_MODEL").split(",") if m.strip()] == []
    with pytest.raises(errors.LLMError, match="no reading model is set up"):
        reader_with(Rationed({}), []).complete(b"%PDF", "hello")


def test_the_daily_rest_lasts_until_the_next_reset():
    reset = datetime(2026, 10, 7, config.AI_DAILY_RESET_UTC_HOUR, 0, tzinfo=timezone.utc)
    assert gemini.seconds_to_daily_reset(reset - timedelta(minutes=30)) == 30 * 60
    assert gemini.seconds_to_daily_reset(reset + timedelta(minutes=30)) == 23.5 * 3600


def test_a_used_up_model_rests_as_long_as_the_service_says(quiet):
    models = Rationed({"m1": PER_DAY.replace("You exceeded your current quota.", "You exceeded your current quota. Please retry in 22h8m29.2s.")})
    reader = reader_with(models, ["m1", "m2"])
    reader.complete(b"%PDF", "hello")
    assert 22 * 3600 < reader.resting["m1"] - gemini.time.monotonic() <= 22 * 3600 + 8 * 60 + 30


def test_a_runaway_chat_reply_is_stopped_and_says_it_was_cut_off(monkeypatch):
    monkeypatch.setattr(pacing, "wait_turn", lambda: None)
    models = Models('{"reply": "8395.49, 8395.4', finish="MAX_TOKENS")
    with pytest.raises(Truncated, match="cut off"):
        reader_with(models).complete(b"%PDF", "hello", kind="chat")
    assert models.caps == [config.AI_CHAT_MAX_REPLY_TOKENS]


def test_reading_a_file_is_not_capped(monkeypatch):
    monkeypatch.setattr(pacing, "wait_turn", lambda: None)
    models = Models('{"documents": []}')
    reader_with(models).complete(b"%PDF", "hello", kind="extract")
    assert models.caps == [None]


def test_tool_calling_is_always_switched_off(monkeypatch):
    monkeypatch.setattr(pacing, "wait_turn", lambda: None)
    for kind in ("extract", "chat"):
        models = Models('{"documents": []}')
        reader_with(models).complete(b"%PDF", "hello", kind=kind)
        assert models.tool_calling_off is True


def test_reading_goes_to_the_reading_models_and_chat_to_the_chat_models(quiet):
    models = Rationed({})
    reader = GeminiAdapter("key", ["flash"], ["lite"])
    reader.client = SimpleNamespace(models=models)
    assert reader.complete(b"%PDF", "read it") == {"by": "lite"}
    assert reader.complete(b"%PDF", "rename a column", kind="chat") == {"by": "flash"}
    assert models.asked == ["lite", "flash"]


def test_without_reading_models_set_everything_uses_the_one_list(quiet):
    models = Rationed({})
    reader = GeminiAdapter("key", ["flash"])
    reader.client = SimpleNamespace(models=models)
    reader.complete(b"%PDF", "read it")
    assert models.asked == ["flash"]
