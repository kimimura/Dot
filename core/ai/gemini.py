import json
import re
import time
from datetime import datetime, timedelta, timezone

import config
from core import activity
from core.ai import pacing
from core.ai.errors import (BUSY, CUT_OFF, DAILY, GARBLED, NO_MODEL, OVERLOAD_MARKERS, RATE_MARKERS, RETRY_MARKERS, LLMError, Truncated,
                            friendly)


def parse_json(text):
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.S)
    a, b = t.find("{"), t.rfind("}")
    if a < 0 or b < a:
        raise ValueError("no JSON object found")
    return json.loads(t[a:b + 1])


def seconds_to_daily_reset(now=None):
    now = now or datetime.now(timezone.utc)
    reset = now.replace(hour=config.AI_DAILY_RESET_UTC_HOUR, minute=0, second=0, microsecond=0)
    return ((reset if reset > now else reset + timedelta(days=1)) - now).total_seconds()


class RateLimited(Exception):
    def __init__(self, seconds, why):
        super().__init__(why)
        self.seconds, self.why = seconds, why


class GeminiAdapter:
    def __init__(self, key, models):
        from google import genai
        from google.genai import types
        # the library's own quiet retries are off: a busy model hands over to the next one straight away
        self.client = genai.Client(api_key=key, http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1)))
        self.models = list(models)
        self.resting = {}

    def complete(self, pdf, prompt, kind="extract"):
        from google.genai import types
        if not self.models:
            raise LLMError(NO_MODEL)
        part = types.Part.from_bytes(data=pdf, mime_type="application/pdf")
        cap = config.AI_CHAT_MAX_REPLY_TOKENS if kind == "chat" else None
        # no tools are ever given, so the library's tool calling is switched off rather than left on by default
        cfg = types.GenerateContentConfig(response_mime_type="application/json", temperature=config.AI_TEMPERATURE, max_output_tokens=cap,
                                          automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
        waited, start = 0.0, time.monotonic()
        # the models are tried in the order given; one that is used up rests and the next one takes over
        while True:
            now = time.monotonic()
            if now - start > config.AI_WAIT_BUDGET:
                raise LLMError(BUSY)
            ready = [m for m in self.models if self.resting.get(m, 0) <= now]
            if not ready:
                if all(self.resting[m] - now > config.AI_WAIT_BUDGET for m in self.models):
                    raise LLMError(DAILY)
                pause = min(self.resting[m] for m in self.models) - now
                if waited + pause > config.AI_WAIT_BUDGET:
                    raise LLMError(BUSY)
                time.sleep(pause)
                waited += pause
                continue
            model = ready[0]
            try:
                return self._ask(model, part, prompt, cfg)
            except RateLimited as e:
                self.resting[model] = time.monotonic() + e.seconds
                nxt = next((m for m in self.models if self.resting.get(m, 0) <= time.monotonic()), None)
                activity.note(f"{model} {e.why}, " + (f"switching to {nxt}" if nxt else "no other model free"))

    def _ask(self, model, part, prompt, cfg):
        def send(p):
            pacing.wait_turn()
            r = self.client.models.generate_content(model=model, contents=[part, p], config=cfg)
            cands = getattr(r, "candidates", None) or []
            if cands and "MAX_TOKENS" in str(getattr(cands[0], "finish_reason", "")):
                raise Truncated(CUT_OFF)
            return r.text

        waited, n = 0.0, 0
        while True:
            try:
                try:
                    return parse_json(send(prompt))
                except ValueError as e:
                    nudge = prompt + f"\n\nYour previous reply was not valid JSON ({e}). Return ONLY the JSON object."
                    return parse_json(send(nudge))
            except ValueError:
                raise LLMError(GARBLED)
            except LLMError:
                raise
            except Exception as e:
                msg = str(e)
                if any(k in msg.lower() for k in RATE_MARKERS):
                    if "perday" in msg.lower() or "per day" in msg.lower():
                        raise RateLimited(seconds_to_daily_reset(), "used up for today")
                    raise RateLimited(pacing.retry_after(msg) or 60, "busy for now")
                if any(k in msg.lower() for k in OVERLOAD_MARKERS):
                    raise RateLimited(config.AI_OVERLOAD_REST, "overloaded")
                if not any(k in msg for k in RETRY_MARKERS):
                    raise LLMError(friendly(e))
                n += 1
                delay = min(2 ** n, config.AI_MAX_WAIT)
                if n > config.AI_MAX_RETRIES or waited + delay > config.AI_WAIT_BUDGET:
                    raise LLMError(BUSY)
                time.sleep(delay + 0.5)
                waited += delay + 0.5
