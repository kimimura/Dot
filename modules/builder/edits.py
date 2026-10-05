import re

from core import pdftext
from modules.builder.review import ask_review
from modules.documents import history, repository as documents, transcript
from modules.reading import column_reread, table_ops, verify


def on_ops(conn, d, pdf, op_list, llm=None):
    if not d.get("table"):
        return d, [{"ok": False, "text": "nothing to edit yet"}]
    history.snapshot(d)
    edited = {k for k, v in (d.get("verification") or {}).get("cells", {}).items() if v == "edited"}
    for o in op_list:
        if o.get("op") == "drop_col":
            d["hints"].append({"scope": "col", "col": str(o.get("col")), "text": f'Do not extract "{o.get("col")}"', "dropped": True})
    table, changes = d["table"], []
    for o in (o for o in op_list if o.get("op") == "reread_cols"):
        table, ch, edited = column_reread.run(llm, pdf, table, o.get("cols") or [o.get("col")], edited, column_notes(d["hints"]))
        changes += ch
    table, more, edited = table_ops.apply_ops(table, [o for o in op_list if o.get("op") != "reread_cols"], edited)
    changes += more
    d["table"] = table
    d["verification"] = verify.verify(table, pdftext.text_of(pdf), d["has_text_layer"], edited=edited)
    alias_hints(d, changes)
    documents.save(conn, d)
    return d, changes


def column_notes(hints):
    return {h["col"]: h["text"] for h in hints if h.get("scope") == "col" and h.get("col") and not h.get("alias") and not h.get("dropped")}


def alias_hints(d, changes):
    for c in changes:
        r = c.get("renamed")
        if r and not re.search(r" \(\d+\)$", r["old"]):
            d["hints"] = [h for h in d["hints"] if not (h.get("scope") == "col" and h.get("alias") == r["old"])]
            d["hints"].append({"scope": "col", "col": r["new"], "alias": r["old"], "text": f'Call the column printed as "{r["old"]}" "{r["new"]}"'})


def on_undo(conn, d, pdf):
    ok = history.undo(d)
    if ok:
        documents.save(conn, d)
    return d, [{"ok": ok, "text": "Undid the last change" if ok else "Nothing to undo"}]


def adopt(conn, d):
    if d["stage"] == "converted":
        d["history"] = []
        ask_review(d, first=True)
        documents.save(conn, d)
    return d


def revise(conn, d):
    d["stage"] = "revising"
    transcript.bot(d, "ask_changes")
    documents.save(conn, d)
    return d
