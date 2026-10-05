import json
from collections import Counter
from difflib import SequenceMatcher

import config
from core import pdftext
from core.ai.errors import LLMError, Truncated
from modules.reading import doc_groups, verify
from modules.reading.extract import plan_chunks
from modules.reading.verify import norm_text


def anchor_column(table, targets):
    rows = table["rows"]
    names = [c["name"] for c in table["columns"] if c.get("kind") != "doc" and c["name"] not in targets]

    def score(name):
        values = [norm_text(r.get(name, "")) for r in rows]
        filled = [v for v in values if len(v) >= 3]
        # codes beat descriptions that tell rows apart about as well: they are copied without slips
        short = -sum(map(len, filled)) / max(len(filled), 1)
        return len(filled) >= config.REREAD_MIN_MATCHED * len(rows), round(len(set(filled)) / max(len(rows), 1), 1), short, -names.index(name)
    best = max(names, key=score, default=None)
    return best if best and score(best)[0] else None


def _prompt(anchor, row_targets, doc_key, doc_targets, notes, part, sample):
    shape = {}
    lines = [f"You are re-reading some columns of a spreadsheet that was extracted from this PDF{part}. "
             "Copy every value exactly as printed. Never guess, and never repeat a value onto an item that does not print it.",
             "What each column holds, from the first rows of the sheet (the columns being re-read may be wrong there; "
             "the column names are the user's own, so go by where each value sits next to the others):",
             json.dumps(sample, ensure_ascii=False)]
    if row_targets:
        shape["rows"] = [[anchor] + row_targets]
        lines.append(f'"rows": one entry per line item on these pages, in page order: its "{anchor}" exactly as printed, '
                     f"then {', '.join(json.dumps(c) for c in row_targets)}.")
    if doc_targets:
        shape["documents"] = [[doc_key or "Document"] + doc_targets]
        lines.append(f'"documents": one entry per document on these pages: its "{doc_key or "first line"}" exactly as printed, '
                     f"then {', '.join(json.dumps(c) for c in doc_targets)}.")
    lines += [f"  - {c}: {t}" for c, t in notes.items() if c in row_targets + doc_targets and t]
    lines.append("Return ONLY a JSON object shaped like " + json.dumps(shape, ensure_ascii=False) + ", with one inner list per item.")
    return "\n".join(lines)


def _expected(rows, anchor, texts, a, b):
    # how many of the sheet's items these pages print, judging by their anchor values
    if not anchor:
        return 0
    text = norm_text("\n".join(texts[a - 1:b]))
    counts = Counter(norm_text(r.get(anchor, "")) for r in rows)
    return sum(min(n, text.count(v)) for v, n in counts.items() if len(v) >= 3)


def _read(llm, pdf, texts, prompt_for, expected=lambda a, b: 0):
    got_rows, got_docs = [], []
    n = len(texts)
    queue = plan_chunks(texts)
    while queue:
        a, b = queue.pop(0)
        part = pdf if (a, b) == (1, n) else pdftext.pages(pdf, a, b)
        try:
            raw = llm.complete(part, prompt_for(a, b, n), kind="extract")
        except Truncated:
            if b - a + 1 <= config.EXTRACT_MIN_SPLIT_PAGES:
                raise
            m = (a + b) // 2
            queue[:0] = [(a, m), (m + 1, b)]
            continue
        raw = raw if isinstance(raw, dict) else {}
        rows = [x for x in raw.get("rows") or [] if isinstance(x, list) and x]
        # dense pages tempt the reader to stop early; fewer items than the pages print means reading them in smaller parts
        if b > a and len(rows) < config.REREAD_MIN_MATCHED * expected(a, b):
            m = (a + b) // 2
            queue[:0] = [(a, m), (m + 1, b)]
            continue
        got_rows += rows
        got_docs += [x for x in raw.get("documents") or [] if isinstance(x, list) and x]
    return got_rows, got_docs


def _same(a, b):
    if a == b or (min(len(a), len(b)) >= 5 and (a in b or b in a)):
        return True
    return min(len(a), len(b)) >= 8 and SequenceMatcher(None, a, b).ratio() >= config.REREAD_SIMILAR


def _line_up(rows, anchor, got):
    # the re-read lists items in page order, the sheet lists them in the same order: walk both together
    found, j = {}, 0
    for i, r in enumerate(rows):
        key = norm_text(r.get(anchor, ""))
        for k in range(j, min(j + config.REREAD_LOOKAHEAD, len(got))):
            if key and _same(key, norm_text(str(got[k][0]))):
                found[i], j = got[k][1:], k + 1
                break
    return found


def _copied_column(rows, found, row_targets, others):
    # a re-read column that just repeats another column was misread: the reader took the wrong field
    for k, name in enumerate(row_targets):
        new = {i: norm_text(str(v[k])) for i, v in found.items() if k < len(v) and norm_text(str(v[k]))}
        for other in others:
            same = sum(1 for i, v in new.items() if v == norm_text(rows[i].get(other, "")))
            if new and same >= config.REREAD_MIN_MATCHED * len(new):
                return name, other
    return None


def _refuse_unprinted(table, rows, old, texts):
    # a re-read value the PDF doesn't print exactly is a misreading: the cell keeps what it had
    if not any(t.strip() for t in texts):
        return []
    text = "\n\n".join(texts)
    before = verify.verify(table, text, True)["cells"]
    after = verify.verify({**table, "rows": rows}, text, True, learn_from=table)["cells"]
    refused = []
    for (i, name), was in old.items():
        key, now = f"{i}|{name}", rows[i][name]
        if now != was and after.get(key) != "ok" and (now or before.get(key) == "ok"):
            rows[i][name] = was
            refused.append(key)
    return refused


def run(llm, pdf, table, cols, edited, notes=None):
    names = {c["name"].lower(): c for c in table["columns"]}
    targets = [names.get(str(c).strip().lower()) for c in cols]
    if not cols or None in targets:
        missing = next((c for c, t in zip(cols, targets) if t is None), None)
        return table, [{"ok": False, "text": f'No column called "{missing}"' if missing else "no column given"}], edited
    row_targets = [c["name"] for c in targets if c.get("kind") != "doc"]
    doc_targets = [c["name"] for c in targets if c.get("kind") == "doc"]
    anchor = anchor_column(table, row_targets) if row_targets else None
    if row_targets and not anchor:
        return table, [{"ok": False, "text": "No column tells the rows apart well enough to re-read them, so nothing changed"}], edited
    doc_key = doc_groups.key_column(table)
    texts = pdftext.page_texts(pdf)
    part = lambda a, b, n: "" if (a, b) == (1, n) else f" (this file is pages {a} to {b} of a {n}-page PDF)"
    try:
        sample = [{c["name"]: r.get(c["name"], "") for c in table["columns"]} for r in table["rows"][:2]]
        got_rows, got_docs = _read(llm, pdf, texts, lambda a, b, n: _prompt(anchor, row_targets, doc_key, doc_targets, notes or {}, part(a, b, n), sample),
                                   lambda a, b: _expected(table["rows"], anchor, texts, a, b))
    except LLMError as e:
        return table, [{"ok": False, "text": f"Re-read failed: {e}"}], edited
    rows = [dict(r) for r in table["rows"]]
    edited = set(edited)
    # a whole column marked as edited came from one bulk edit, not from a person typing every cell
    bulk = {c["name"] for c in targets if all(f"{i}|{c['name']}" in edited for i in range(len(rows)))}
    edited -= {f"{i}|{name}" for name in bulk for i in range(len(rows))}
    kept = sum(1 for k in edited if k.split("|", 1)[1] in row_targets + doc_targets)
    found = _line_up(rows, anchor, got_rows) if row_targets else {}
    if row_targets and len(found) < config.REREAD_MIN_MATCHED * len(rows):
        return table, [{"ok": False, "text": f"The re-read didn't line up with the sheet ({len(found)} of {len(rows)} rows), so nothing changed"}], edited
    copied = _copied_column(rows, found, row_targets, [c["name"] for c in table["columns"] if c["name"] not in row_targets])
    if copied:
        return table, [{"ok": False, "text": f'The re-read put "{copied[1]}" values into "{copied[0]}", so nothing changed'}], edited
    old = {}
    for i, values in found.items():
        for name, v in zip(row_targets, values):
            if f"{i}|{name}" not in edited:
                old[(i, name)], rows[i][name] = rows[i].get(name, ""), "" if v is None else str(v)
    by_doc = {norm_text(str(x[0])): x[1:] for x in got_docs}
    for i, r in enumerate(rows):
        values = by_doc.get(norm_text(r.get(doc_key, ""))) if doc_key else (got_docs[0][1:] if got_docs else None)
        for name, v in zip(doc_targets, values or []):
            if f"{i}|{name}" not in edited:
                old[(i, name)], r[name] = r.get(name, ""), "" if v is None else str(v)
    label = ", ".join(f'"{c["name"]}"' for c in targets)
    if not old:
        return table, [{"ok": False, "text": f"Nothing to re-read in {label}: every cell there was typed by hand"}], edited
    refused = _refuse_unprinted(table, rows, old, texts)
    if refused and all(rows[i][name] == was for (i, name), was in old.items()):
        return table, [{"ok": False, "text": f"Nothing changed in {label}: the values that differed from the sheet don't match the PDF"}], edited
    detail = f"{len(found)} of {len(rows)} rows" if row_targets else f"{len(by_doc)} documents"
    note = f", {kept} cells typed by hand kept" if kept else ""
    note += f", {len(refused)} cells left as they were because the new value doesn't match the PDF" if refused else ""
    return {**table, "rows": rows}, [{"ok": True, "text": f"Re-read {label} from the PDF ({detail}{note})"}], edited
