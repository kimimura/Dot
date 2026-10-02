import json
import re

from core.ai.errors import LLMError


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
        cols, order = [], []
        for c in d.get("row_columns") or []:
            c = _clean_name(c)
            order.append(c)
            if c and c not in cols:
                cols.append(c)
        rows = []
        for r in d.get("rows") or []:
            if isinstance(r, list):
                r = {order[i]: v for i, v in enumerate(r) if i < len(order) and order[i]}
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
