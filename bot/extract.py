import json
import re

from .llm import LLMError

DOC_KINDS = "invoice|purchase_order|receipt|statement|delivery_note|quotation|form|report|letter|other"

SCHEMA_TEXT = f"""Return ONLY a JSON object with this exact shape:
{{
  "signature": {{"title": "document title or type as printed", "issuer": "organisation that produced it", "doc_kind": "{DOC_KINDS}"}},
  "documents": [
    {{
      "document_fields": {{"Field Name": "value as printed", "...": "..."}},
      "row_columns": ["Column A", "Column B", "..."],
      "rows": [{{"Column A": "value", "Column B": "value"}}, {{"...": "..."}}]
    }}
  ],
  "extra_fields": {{}}
}}
Rules:
- One entry in "documents" per distinct document inside the file (most files contain exactly one).
- "document_fields" are values that appear once per document: reference numbers, dates, names, addresses, totals, terms.
- "rows" are the repeating line items (products, transactions, entries). "row_columns" lists their column names in the order printed. If there are no repeating items, use [] for both.
- Copy values exactly as printed, including number formatting. Use "" when a value is absent. Every value is a string.
- Column and field names: short, Title Case, unique, no trailing colons.
"""

FRESH_PROMPT = """You are reading a PDF and turning it into a spreadsheet. Extract every field and every repeating row a person would want in a spreadsheet for this kind of document. Do not invent values.

""" + SCHEMA_TEXT


def profile_prompt(profile, hints):
    doc_cols = [c for c in profile["columns"] if c.get("kind") == "doc"]
    row_cols = [c for c in profile["columns"] if c.get("kind") != "doc"]

    def fmt(cols):
        return "\n".join(f'  - "{c["name"]}"' + (f' — {c["hint"]}' if c.get("hint") else "") for c in cols) or "  (none)"

    lines = [
        f'You are reading a PDF in a known format called "{profile["name"]}". Produce exactly the columns below, using these exact names. Use "" for any column that is absent in this document. Do not add other columns to the table.',
        "", "Document-level fields (once per document):", fmt(doc_cols),
        "", "Row-level columns (one per repeating line item):", fmt(row_cols),
    ]
    rules = [h["text"] for h in profile.get("hints", [])] + [h["text"] for h in hints if h.get("scope") != "col"]
    if rules:
        lines += ["", "Rules learned from previous documents of this format:"] + [f"  - {r}" for r in rules]
    ex = (profile.get("examples") or [None])[0]
    if ex and ex.get("rows"):
        lines += ["", "Example rows from a previous document of this format:", json.dumps(ex["rows"][:2], ensure_ascii=False)]
    lines += ["", 'If you notice useful fields that are NOT in the list, put them in "extra_fields" (name → value) instead of the table.', "", SCHEMA_TEXT]
    return "\n".join(lines)


def build_prompt(profile=None, hints=None, instruction=None):
    p = profile_prompt(profile, hints or []) if profile else FRESH_PROMPT
    if hints and not profile:
        p += "\nAdditional rules from the user:\n" + "\n".join(f"  - {h['text']}" for h in hints if h.get("text"))
    if instruction:
        p += f"\n\nThe user asked for this change to the extraction — follow it precisely:\n{instruction}\n"
    return p


# ── validation + flatten ─────────────────────────────────────────────────────

def _s(v):
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return str(v).strip()


def _clean_name(n):
    n = re.sub(r"\s+", " ", _s(n)).strip(" :")
    return n[:60]


def validate(raw):
    if not isinstance(raw, dict):
        raise LLMError("the model returned something that isn't an object")
    sig = raw.get("signature") or {}
    signature = {"title": _s(sig.get("title"))[:120], "issuer": _s(sig.get("issuer"))[:120], "doc_kind": _s(sig.get("doc_kind")) or "other"}
    docs_in = raw.get("documents")
    if not isinstance(docs_in, list) or not docs_in:
        docs_in = [{"document_fields": raw.get("document_fields") or {}, "row_columns": raw.get("row_columns") or [], "rows": raw.get("rows") or []}]
    docs = []
    for d in docs_in:
        if not isinstance(d, dict):
            continue
        fields = {}
        for k, v in (d.get("document_fields") or {}).items():
            k = _clean_name(k)
            if k:
                fields[k] = _s(v)
        cols = []
        for c in d.get("row_columns") or []:
            c = _clean_name(c)
            if c and c not in cols:
                cols.append(c)
        rows = []
        for r in d.get("rows") or []:
            if not isinstance(r, dict):
                continue
            row = {}
            for k, v in r.items():
                k = _clean_name(k)
                if not k:
                    continue
                if k not in cols:
                    cols.append(k)
                row[k] = _s(v)
            if any(row.values()):
                rows.append(row)
        docs.append({"document_fields": fields, "row_columns": cols, "rows": rows})
    if not docs:
        raise LLMError("the model returned no documents")
    extra = {_clean_name(k): _s(v) for k, v in (raw.get("extra_fields") or {}).items() if _clean_name(k)}
    return {"signature": signature, "documents": docs, "extra_fields": extra}


def flatten(parsed):
    doc_names, row_names = [], []
    for d in parsed["documents"]:
        for k in d["document_fields"]:
            if k not in doc_names:
                doc_names.append(k)
        for k in d["row_columns"]:
            if k not in row_names:
                row_names.append(k)
    renames = {}
    for k in list(row_names):
        if k in doc_names:
            renames[k] = k + " (Line)"
    row_names = [renames.get(k, k) for k in row_names]
    columns = [{"name": n, "kind": "doc"} for n in doc_names] + [{"name": n, "kind": "row"} for n in row_names]
    rows = []
    for i, d in enumerate(parsed["documents"]):
        base = {n: d["document_fields"].get(n, "") for n in doc_names}
        if d["rows"]:
            for r in d["rows"]:
                row = {"_doc": i, **base}
                for n in row_names:
                    row[n] = ""
                for k, v in r.items():
                    row[renames.get(k, k)] = v
                rows.append(row)
        else:
            row = {"_doc": i, **base}
            for n in row_names:
                row[n] = ""
            rows.append(row)
    return {"columns": columns, "rows": rows}


# ── verification against the text layer ─────────────────────────────────────

def _norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


MAX_GAP = 200
MAX_ANCHORS = 80


def _chain(parts, hay, at):
    for p in parts[1:]:
        i = hay.find(p, at)
        if i < 0 or i - at > MAX_GAP:
            return False
        at = i + len(p)
    return True


def _found(value, hay):
    n = _norm(value)
    if not n or len(n) <= 2 or n in hay:
        return True
    parts = [_norm(p) for p in re.split(r"\s+", value.strip()) if _norm(p)]
    if not parts:
        return True
    if len(parts) == 1:
        return parts[0] in hay
    at = 0
    for _ in range(MAX_ANCHORS):
        i = hay.find(parts[0], at)
        if i < 0:
            return False
        if _chain(parts, hay, i + len(parts[0])):
            return True
        at = i + 1
    return False


def verify(table, text, has_text_layer, edited=None, previous=None):
    edited = edited or set()
    prev = (previous or {}).get("cells", {})
    cells, ok, total = {}, 0, 0
    hay = _norm(text) if has_text_layer else ""
    seen = {}
    for r, row in enumerate(table["rows"]):
        for c in table["columns"]:
            key = f"{r}|{c['name']}"
            v = row.get(c["name"], "")
            if not v:
                cells[key] = "na"
                continue
            total += 1
            if key in edited or prev.get(key) == "edited":
                cells[key] = "edited"
                ok += 1
            elif not has_text_layer:
                cells[key] = "na"
            else:
                if v not in seen:
                    seen[v] = _found(v, hay)
                cells[key] = "ok" if seen[v] else "miss"
                ok += 1 if seen[v] else 0
    return {"cells": cells, "verified": ok, "total": total, "checked": has_text_layer}


def run(llm, pdf_path, profile=None, hints=None, instruction=None):
    prompt = build_prompt(profile, hints, instruction)
    raw = llm.complete(pdf_path, prompt, kind="extract")
    parsed = validate(raw)
    table = flatten(parsed)
    if profile:
        table = _conform(table, profile)
    return table, parsed["signature"], parsed["extra_fields"]


def _conform(table, profile):
    have = {c["name"].lower(): c["name"] for c in table["columns"]}
    src_for, used = {}, set()
    for c in profile["columns"]:
        for cand in [c["name"]] + list(c.get("aliases") or []):
            if cand.lower() in have and have[cand.lower()] not in used:
                src_for[c["name"]] = have[cand.lower()]
                used.add(have[cand.lower()])
                break
    columns = [{"name": c["name"], "kind": c.get("kind", "row")} for c in profile["columns"]]
    columns += [c for c in table["columns"] if c["name"] not in used and c["name"].lower() not in {x["name"].lower() for x in columns}]
    rows = []
    for r in table["rows"]:
        nr = {"_doc": r.get("_doc", 0)}
        for c in columns:
            nr[c["name"]] = r.get(src_for.get(c["name"], c["name"]), "")
        rows.append(nr)
    return {"columns": columns, "rows": rows}
