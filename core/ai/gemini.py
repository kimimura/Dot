import ast
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


def retry_in(msg):
    # the wait the service names itself, e.g. "Please retry in 22h8m29.2s"
    m = re.search(r"retry in (?:(\d+)h)?(?:(\d+)m(?!s))?(?:([\d.]+)s?)?", msg, re.I)
    if not m or not any(m.groups()):
        return None
    h, mins, s = (float(x) if x else 0.0 for x in m.groups())
    return h * 3600 + mins * 60 + s


class RateLimited(Exception):
    def __init__(self, seconds, why, said, daily=False):
        super().__init__(why)
        self.seconds, self.why, self.said, self.daily = seconds, why, said, daily


class GeminiAdapter:
    def __init__(self, key, models, read_models=None):
        from google import genai
        from google.genai import types
        # the library's own quiet retries are off: every try is one of Dot's, so it is counted and spaced
        self.client = genai.Client(api_key=key, http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1)))
        # reading a PDF follows no instructions of the user's, so it can go to models with more room; chat edits get the ones that follow instructions best
        self.models, self.read_models = list(models), list(read_models or models)
        self.resting = {}

    def complete(self, pdf, prompt, kind="extract"):
        from google.genai import types
        chain = self.read_models if kind == "extract" else self.models
        if not chain:
            raise LLMError(NO_MODEL)
        part = types.Part.from_bytes(data=pdf, mime_type="application/pdf")
        cap = config.AI_CHAT_MAX_REPLY_TOKENS if kind == "chat" else None
        # no tools are ever given, so the library's tool calling is switched off rather than left on by default
        cfg = types.GenerateContentConfig(response_mime_type="application/json", temperature=config.AI_TEMPERATURE, max_output_tokens=cap,
                                          automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
        # only a model used up for the day hands over to the next; a busy one is waited for and tried again, so tries stay few.
        # each line gives the service's own words, then what happens next
        waits = list(config.AI_BUSY_WAITS)
        while True:
            model = next((m for m in chain if self.resting.get(m, 0) <= time.monotonic()), None)
            if model is None:
                raise LLMError(DAILY)
            try:
                return self._ask(model, part, prompt, cfg)
            except RateLimited as e:
                if e.daily:
                    self.resting[model] = time.monotonic() + e.seconds
                    nxt = next((m for m in chain if self.resting.get(m, 0) <= time.monotonic()), None)
                    activity.note(f"{model}: {e.said} — " + (f"switching to {nxt}" if nxt else "no other model left"))
                    continue
                if not waits:
                    activity.note(f"{model}: {e.said} — tried {len(config.AI_BUSY_WAITS) + 1} times, giving up")
                    raise LLMError(BUSY)
                pause = max(e.seconds, waits.pop(0))
                activity.note(f"{model}: {e.said} — trying again in {_minutes(pause)}")
                time.sleep(pause)

    def _ask(self, model, part, prompt, cfg):
        def send(p):
            pacing.wait_turn()
            r = self.client.models.generate_content(model=model, contents=[part, p], config=cfg)
            cands = getattr(r, "candidates", None) or []
            if cands and "MAX_TOKENS" in str(getattr(cands[0], "finish_reason", "")):
                raise Truncated(CUT_OFF)
            return r.text

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
            low, said = msg.lower(), google_said(msg)
            if any(k in low for k in RATE_MARKERS):
                if "perday" in low or "per day" in low:
                    raise RateLimited(retry_in(msg) or seconds_to_daily_reset(), "used up for today", said, daily=True)
                raise RateLimited(retry_in(msg) or pacing.retry_after(msg) or 0, "busy for now", said)
            if any(k in low for k in OVERLOAD_MARKERS):
                raise RateLimited(0, "overloaded", said)
            if any(k in msg for k in RETRY_MARKERS):
                raise RateLimited(0, "not answering", said)
            activity.note(f"{model}: {said} — stopped")
            raise LLMError(friendly(e))


def google_said(msg):
    # the code, status and message exactly as the service gave them, on one line for the terminal
    head, _, body = msg.partition(". {")
    try:
        text = ast.literal_eval("{" + body)["error"]["message"]
    except Exception:
        head, text = "", msg
    said = " ".join(str(text).split())
    return (f"{head}: " if head else "") + said[:config.AI_SAID_MAX_CHARS]


def _minutes(seconds):
    m = round(seconds / 60)
    return f"{m} min" if m >= 1 else f"{round(seconds)} s"
