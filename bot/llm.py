import json
import os
import re
import time
from pathlib import Path

import pdfplumber

OFFLINE = ("offline", "fake", "none")
RETRY_MARKERS = ("429", "500", "502", "503", "504", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "DEADLINE", "overloaded")


class LLMError(Exception):
    pass


def _env(*names, default=""):
    for n in names:
        v = os.environ.get(n, "").strip()
        if v:
            return v
    return default


def api_key():
    return _env("LLM_API_KEY", "GEMINI_API_KEY", "API_KEY")


def model_name():
    return _env("LLM_MODEL", "GEMINI_MODEL", default=GeminiAdapter.default_model)


def status():
    if _env("LLM_PROVIDER").lower() in OFFLINE:
        return "offline"
    return "gemini" if api_key() else "offline"


_cache = {}


def get_llm():
    if status() == "offline":
        return OfflineAdapter()
    key = (api_key(), model_name())
    if key not in _cache:
        _cache.clear()
        _cache[key] = GeminiAdapter(*key)
    return _cache[key]


def parse_json(text):
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.S)
    a, b = t.find("{"), t.rfind("}")
    if a < 0 or b < a:
        raise ValueError("no JSON object found")
    return json.loads(t[a:b + 1])


def friendly(e):
    m = str(e)
    low = m.lower()
    if "api_key_invalid" in low or "api key not valid" in low or "authentication" in low or "401" in m:
        return "the API key was rejected"
    if "429" in m or "resource_exhausted" in low or "rate limit" in low or "quota" in low:
        return "the model is rate-limited right now"
    if "permission_denied" in low or "403" in m:
        return "the model refused the request (permission denied)"
    if "404" in m or ("not found" in low and "model" in low):
        return "that model name doesn't exist for this key"
    return m[:180]


class GeminiAdapter:
    default_model = "gemini-2.5-flash"

    def __init__(self, key, model):
        from google import genai
        self.client = genai.Client(api_key=key)
        self.model = model or self.default_model

    def complete(self, pdf_path, prompt, kind="extract"):
        from google.genai import types
        part = types.Part.from_bytes(data=Path(pdf_path).read_bytes(), mime_type="application/pdf")
        cfg = types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1)

        def send(p):
            return self.client.models.generate_content(model=self.model, contents=[part, p], config=cfg).text

        last = None
        for n in range(3):
            try:
                try:
                    return parse_json(send(prompt))
                except ValueError as e:
                    nudge = prompt + f"\n\nYour previous reply was not valid JSON ({e}). Return ONLY the JSON object."
                    return parse_json(send(nudge))
            except ValueError as e:
                raise LLMError(f"the model returned malformed data ({e})")
            except Exception as e:
                last = e
                if n < 2 and any(m in str(e) for m in RETRY_MARKERS):
                    time.sleep(2 * (n + 1))
                    continue
                raise LLMError(friendly(e))
        raise LLMError(friendly(last))


class OfflineAdapter:
    default_model = "offline"

    def __init__(self, *_):
        self.model = "offline"

    def complete(self, pdf_path, prompt, kind="extract"):
        return self._chat(prompt) if kind == "chat" else self._extract(pdf_path)

    def _extract(self, pdf_path):
        fields, header, rows, title, issuer = {}, [], [], "", ""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                p1 = pdf.pages[0]
                lines = [l.strip() for l in (p1.extract_text() or "").splitlines() if l.strip()]
                title = lines[0] if lines else "Document"
                issuer = lines[1] if len(lines) > 1 else ""
                for l in lines[:40]:
                    m = re.match(r"^([A-Za-z][A-Za-z .#/]{1,30}?)\s*[:：]\s*(.+)$", l)
                    if m and len(fields) < 8:
                        fields[m.group(1).strip().title()] = m.group(2).strip()
                for page in pdf.pages[:5]:
                    for tb in page.extract_tables() or []:
                        if not tb or len(tb) < 2:
                            continue
                        if not header:
                            header = [str(c or f"Column {i + 1}").strip() for i, c in enumerate(tb[0])]
                            body = tb[1:]
                        else:
                            body = tb[1:] if [str(c or "").strip() for c in tb[0]] == header else tb
                        for r in body:
                            if any((c or "").strip() for c in r):
                                rows.append({header[i]: str(r[i] or "").strip() for i in range(min(len(header), len(r)))})
        except Exception:
            pass
        if not fields and not rows:
            fields = {"Title": title or "Document", "Note": "Offline mode found no structure"}
        return {"signature": {"title": title, "issuer": issuer, "doc_kind": "other"},
                "documents": [{"document_fields": fields, "row_columns": header, "rows": rows}]}

    def _chat(self, prompt):
        msg = prompt.rsplit("USER MESSAGE:", 1)[-1].strip().splitlines()[0].strip().strip('"')
        low = msg.lower()
        ops, hints = [], []
        m = re.search(r"rename\s+(.+?)\s+(?:to|as)\s+(.+)", msg, re.I)
        if m:
            ops.append({"op": "rename_col", "col": m.group(1).strip(' "\''), "new_name": m.group(2).strip(' ".\'')})
            hints.append({"scope": "col", "col": m.group(2).strip(' ".\''), "text": f'Call this column "{m.group(2).strip(" .")}"'})
        m = re.search(r"(?:drop|remove|delete)\s+(?:the\s+)?(?:column\s+)?(.+)", msg, re.I)
        if m and not ops:
            ops.append({"op": "drop_col", "col": m.group(1).strip(' ".\'')})
        m = re.search(r"(upper|lower)case\s+(.+)", msg, re.I)
        if m and not ops:
            ops.append({"op": "transform_col", "col": m.group(2).strip(' ".\''), "kind": m.group(1).lower()})
        if re.match(r"^(y|yes|yeah|yep|yup|correct|right|ok|okay|sure|looks good)\b", low):
            return {"reply": "Great.", "intent": "confirm", "ops": [], "hints": []}
        if re.match(r"^(n|no|nope|wrong|not (quite|really))\b", low):
            return {"reply": "Okay.", "intent": "reject", "ops": [], "hints": []}
        if ops:
            return {"reply": "Done — I applied that.", "intent": "edit", "ops": ops, "hints": hints}
        if low.endswith("?"):
            return {"reply": "I'm running offline, so I can only rename, drop, or uppercase/lowercase columns right now.",
                    "intent": "question", "ops": [], "hints": []}
        return {"reply": "Offline, I understand 'rename X to Y', 'drop X', and 'uppercase X'.",
                "intent": "offtopic", "ops": [], "hints": []}
