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
    plain = [o for o in op_list if o.get("op") != "reread_cols"]
    table, more, edited = table_ops.apply_ops(table, plain, edited)
    changes += more
    d["table"], d["hints"] = table, settle_hints(d["hints"], plain, more, table)
    d["verification"] = verify.verify(table, pdftext.text_of(pdf), d["has_text_layer"], edited=edited)
    alias_hints(d, changes)
    documents.save(conn, d)
    return d, changes


def column_notes(hints):
    return {h["col"]: h["text"] for h in hints if h.get("scope") == "col" and h.get("col") and not h.get("alias") and not h.get("dropped")}


def alias_hints(d, changes):
    # a column made by an edit was never printed on the PDF, so renaming it says nothing about the PDF's own headers
    made = {c["filled"] for c in changes if c.get("filled") and c["filled"] != c.get("source")}
    for c in changes:
        r = c.get("renamed")
        if r and not re.search(r" \(\d+\)$", r["old"]) and r["old"] not in made:
            d["hints"] = [h for h in d["hints"] if not (h.get("scope") == "col" and h.get("alias") == r["old"])]
            d["hints"].append({"scope": "col", "col": r["new"], "alias": r["old"], "text": f'Call the column printed as "{r["old"]}" "{r["new"]}"'})


def settle_hints(hints, ops, changes, table):
    names = {c["name"].lower() for c in table["columns"]}
    # a dropped column's name in use again (a cleaned copy renamed back) is no longer a column to leave out
    hints = [h for h in hints if not (h.get("dropped") and str(h.get("col", "")).lower() in names)]
    renamed = {c["renamed"]["old"]: c["renamed"]["new"] for c in changes if c.get("ok") and c.get("renamed")}
    for o, c in zip(ops, changes):
        if o.get("op") != "extract_col" or not c.get("ok") or not o.get("pattern"):
            continue
        name = c["filled"]
        while name in renamed:
            name = renamed[name]
        has_rule = any(h.get("scope") == "col" and h.get("col") == name and not h.get("alias") and not h.get("dropped") for h in hints)
        if name.lower() in names and not has_rule:
            hints.append({"scope": "col", "col": name, "text": f'Extract only the part of "{c["source"]}" that matches the pattern {o["pattern"]}'})
    return hints


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
