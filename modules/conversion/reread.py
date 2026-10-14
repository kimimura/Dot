from core import activity, db, pdftext
from modules.conversion import reading
from modules.documents import repository as documents
from modules.profiles import repository as profiles


def start(conn, d):
    if d["stage"] == "rereading":
        return d, [{"ok": False, "text": "Already re-reading this file"}]
    if d["stage"] not in ("confirmed", "converted") or not d.get("table"):
        return d, [{"ok": False, "text": "Only finished files can be re-read"}]
    if not d.get("profile_id") or not profiles.get(conn, d["profile_id"]):
        return d, [{"ok": False, "text": "This file has no saved format to re-read with"}]
    d["reread_from"], d["stage"], d["reread_error"] = d["stage"], "rereading", None
    documents.save(conn, d)
    return d, [{"ok": True, "text": "Re-reading with the current format"}]


def run(conn, d, pdf):
    # "current format" means what the format has learned: the same answer every time, never a model
    prof = profiles.get(conn, d["profile_id"]) if d.get("profile_id") else None
    if not prof:
        d["reread_error"] = "its format was deleted"
        return d
    table, ver, note = reading.read_direct(conn, d, prof, pdftext.page_texts(pdf)) if d["has_text_layer"] else (None, None, "scanned")
    if not table:
        d["reread_error"] = f"doesn't fit the current {prof['name']} format ({note}); open it in Profile Builder"
        activity.note(f"Re-read {d['filename']}: {d['reread_error']}")
        return d
    d["reread_changes"] = changes(d["table"], table)
    # a re-read that changed nothing leaves nothing to undo
    d["before_reread"] = {"table": d["table"], "verification": d["verification"]} if d["reread_changes"] != NOTHING else None
    d["table"], d["verification"] = table, ver
    d["reread_at"], d["reread_error"] = db.now(), None
    activity.note(f"Re-read {d['filename']} with the {prof['name']} format: {d['reread_changes']}")
    return d


NOTHING = "nothing changed"


def changes(old, new):
    # what a re-read did to the sheet, in a line: columns that came or went, rows added or lost, and cells that changed per column
    said = []
    before, after = [c["name"] for c in old["columns"]], [c["name"] for c in new["columns"]]
    said += [f'"{c}" added' for c in after if c not in before] + [f'"{c}" gone' for c in before if c not in after]
    a, b = len(old["rows"]), len(new["rows"])
    if a != b:
        said.append(f"{b} rows instead of {a}")
    for c in (c for c in after if c in before):
        n = sum(1 for x, y in zip(old["rows"], new["rows"]) if (x.get(c) or "") != (y.get(c) or ""))
        if n:
            said.append(f'"{c}" changed in {n} of {min(a, b)} rows')
    return "; ".join(said) or NOTHING


def undo(conn, d):
    prev = d.get("before_reread")
    if not prev:
        return d, [{"ok": False, "text": "Nothing to undo"}]
    d["table"], d["verification"] = prev["table"], prev["verification"]
    d["before_reread"], d["reread_at"], d["reread_changes"] = None, None, None
    documents.save(conn, d)
    return d, [{"ok": True, "text": "Put back the sheet from before the re-read"}]
