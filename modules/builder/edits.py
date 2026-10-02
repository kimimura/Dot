import re

from core import pdftext
from modules.builder.review import ask_review
from modules.documents import history, repository as documents, transcript
from modules.reading import table_ops, verify


def on_ops(conn, d, pdf, op_list):
    if not d.get("table"):
        return d, [{"ok": False, "text": "nothing to edit yet"}]
    history.snapshot(d)
    edited = {k for k, v in (d.get("verification") or {}).get("cells", {}).items() if v == "edited"}
    for o in op_list:
        if o.get("op") == "drop_col":
            d["hints"].append({"scope": "col", "col": str(o.get("col")), "text": f'Do not extract "{o.get("col")}"', "dropped": True})
    table, changes, edited = table_ops.apply_ops(d["table"], op_list, edited)
    d["table"] = table
    d["verification"] = verify.verify(table, pdftext.text_of(pdf), d["has_text_layer"], edited=edited)
    alias_hints(d, changes)
    documents.save(conn, d)
    return d, changes


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
