import io
import re

import pdfplumber


class OfflineAdapter:
    default_model = "offline"

    def __init__(self, *_):
        self.model = "offline"

    def complete(self, pdf, prompt, kind="extract"):
        return self._chat(prompt) if kind == "chat" else self._extract(pdf)

    def _extract(self, pdf):
        fields, header, rows, title, issuer = {}, [], [], "", ""
        try:
            with pdfplumber.open(io.BytesIO(pdf)) as pdf:
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
        if re.search(r"\b(revert|undo|go back)\b", low):
            return {"reply": "Rolled that back.", "intent": "edit", "ops": [{"op": "undo", "steps": 1}], "hints": []}
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
