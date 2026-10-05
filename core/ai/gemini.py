import json
import re
import time

import config
from core.ai import pacing
from core.ai.errors import BUSY, CUT_OFF, GARBLED, RATE_MARKERS, RETRY_MARKERS, LLMError, Truncated, friendly


def parse_json(text):
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.S)
    a, b = t.find("{"), t.rfind("}")
    if a < 0 or b < a:
        raise ValueError("no JSON object found")
    return json.loads(t[a:b + 1])


class GeminiAdapter:
    def __init__(self, key, model):
        from google import genai
        self.client = genai.Client(api_key=key)
        self.model = model

    def complete(self, pdf, prompt, kind="extract"):
        from google.genai import types
        part = types.Part.from_bytes(data=pdf, mime_type="application/pdf")
        cap = config.AI_CHAT_MAX_REPLY_TOKENS if kind == "chat" else None
        cfg = types.GenerateContentConfig(response_mime_type="application/json", temperature=config.AI_TEMPERATURE, max_output_tokens=cap)

        def send(p):
            pacing.wait_turn()
            r = self.client.models.generate_content(model=self.model, contents=[part, p], config=cfg)
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
                if not any(k in msg for k in RETRY_MARKERS) or "PerDay" in msg:
                    raise LLMError(friendly(e))
                n += 1
                rate = any(k in msg.lower() for k in RATE_MARKERS)
                delay = min((pacing.retry_after(msg) if rate else None) or 2 ** n, config.AI_MAX_WAIT)
                if n > config.AI_MAX_RETRIES or waited + delay > config.AI_WAIT_BUDGET:
                    raise LLMError(BUSY)
                time.sleep(delay + 0.5)
                waited += delay + 0.5
