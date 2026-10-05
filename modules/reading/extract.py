import config
from core import pdftext
from core.ai.errors import Truncated
from modules.reading import doc_groups
from modules.reading.parse import flatten, validate
from modules.reading.prompts import build_prompt
from modules.reading.verify import norm_text


def plan_chunks(texts):
    n = len(texts)
    if sum(len(t.strip()) for t in texts) / max(n, 1) < 40:
        return [(a, min(a + config.EXTRACT_SCAN_CHUNK_PAGES - 1, n)) for a in range(1, n + 1, config.EXTRACT_SCAN_CHUNK_PAGES)]
    out, a, size = [], 1, 0
    for i, t in enumerate(texts, 1):
        if i > a and (size + len(t) > config.EXTRACT_CHUNK_CHARS or i - a >= config.EXTRACT_CHUNK_PAGES):
            out.append((a, i - 1))
            a, size = i, 0
        size += len(t)
    out.append((a, n))
    return out


def _item_page(norm):
    digits = sum(ch.isdigit() for ch in norm)
    return len(norm) >= 200 and digits >= 0.15 * len(norm)


def coverage(t, norm_pages, a, b):
    # a row pins a page only when its value and its document's id are both on it; values alone repeat across documents
    rcols = [c["name"] for c in t["columns"] if c.get("kind") != "doc"]
    dcols = [c["name"] for c in t["columns"] if c.get("kind") == "doc"]
    pages = [p for p in range(a, b + 1) if _item_page(norm_pages[p - 1])]
    if not rcols or not pages:
        return 1.0
    key = max(dcols, key=lambda c: len({r.get(c, "") for r in t["rows"]}), default=None)
    span = range(a, b + 1)
    hit = set()
    for r in t["rows"]:
        rv = max((norm_text(r.get(c, "")) for c in rcols), key=len, default="")
        if len(rv) < 6:
            continue
        dv = norm_text(r.get(key, "")) if key else ""
        on = [p for p in span if rv in norm_pages[p - 1]]
        both = [p for p in on if len(dv) >= 4 and dv in norm_pages[p - 1]]
        hit.update(both or on)
    return len(hit.intersection(pages)) / len(pages)


def _halves(a, b):
    m = (a + b) // 2
    return [(a, m), (m + 1, b)]


def run(llm, pdf, profile=None, hints=None, instruction=None, progress=None, texts=None):
    texts = texts if texts is not None else pdftext.page_texts(pdf)
    n = len(texts)
    queue = plan_chunks(texts)
    whole = queue == [(1, n)]
    norm_pages = None if whole else [norm_text(t) for t in texts]
    table = sig = template = None
    extra, done = {}, 0
    budget = config.EXTRACT_MAX_EXTRA_READS * len(queue)
    while queue:
        a, b = queue.pop(0)
        if progress and not whole:
            progress(done, n)
        part = pdf if (a, b) == (1, n) else pdftext.pages(pdf, a, b)
        prompt = build_prompt(template or profile, hints, instruction, fresh=profile is None)
        if (a, b) != (1, n):
            prompt += _chunk_note(a, b, n)
        try:
            parsed = validate(llm.complete(part, prompt, kind="extract"))
        except Truncated:
            if b - a + 1 <= config.EXTRACT_MIN_SPLIT_PAGES:
                raise
            queue[:0] = _halves(a, b)
            continue
        t = flatten(parsed)
        if template or profile:
            t = _conform(t, template or profile)
        if not whole and budget > 0 and b - a + 1 > config.EXTRACT_MIN_SPLIT_PAGES and coverage(t, norm_pages, a, b) < config.EXTRACT_COVERAGE_OK:
            budget -= 1
            queue[:0] = _halves(a, b)
            continue
        if table is None:
            table, sig = t, parsed["signature"]
            if not profile and not whole:
                template = {"name": "this document", "columns": [dict(c) for c in t["columns"]], "hints": [],
                            "examples": [{"rows": [{k: v for k, v in r.items() if k != "_doc"} for r in t["rows"][:2]]}]}
        else:
            _append(table, t)
        for k, v in parsed["extra_fields"].items():
            extra.setdefault(k, v)
        done += b - a + 1
    if progress and not whole:
        progress(n, n)
    return doc_groups.join_pages(table), sig, extra


def _chunk_note(a, b, n):
    return (f"\n\nThis file is pages {a} to {b} of a {n}-page PDF. Extract only what is on these pages. "
            "If the first rows continue a document that began on an earlier page and carry no header of their own, "
            "leave that document's fields empty rather than guessing.\n")


def _append(base, t):
    names = [c["name"] for c in base["columns"]]
    for c in t["columns"]:
        if c["name"] not in names:
            base["columns"].append(dict(c))
            names.append(c["name"])
            for r in base["rows"]:
                r[c["name"]] = ""
    doc_cols = [c["name"] for c in base["columns"] if c.get("kind") == "doc"]
    last = base["rows"][-1] if base["rows"] else None
    offset = (max(r.get("_doc", 0) for r in base["rows"]) + 1) if base["rows"] else 0
    first = t["rows"][0].get("_doc", 0) if t["rows"] else 0
    for r in t["rows"]:
        r = {**{k: "" for k in names}, **r}
        carries_on = last is not None and r.get("_doc", 0) == first and all(r.get(k, "") in ("", last.get(k, "")) for k in doc_cols)
        if carries_on:
            for k in doc_cols:
                r[k] = last.get(k, "")
            r["_doc"] = last["_doc"]
        else:
            r["_doc"] = r.get("_doc", 0) + offset
        base["rows"].append(r)


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
