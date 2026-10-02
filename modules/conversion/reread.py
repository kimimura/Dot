from core import db, pdftext
from core.ai.errors import LLMError
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


def run(conn, llm, d, pdf):
    prof = profiles.get(conn, d["profile_id"]) if d.get("profile_id") else None
    if not prof:
        raise LLMError("its format was deleted")
    table, ver, _ = reading.read_with_model(llm, d, pdf, prof, pdftext.page_texts(pdf))
    d["before_reread"] = {"table": d["table"], "verification": d["verification"]}
    d["table"], d["verification"] = table, ver
    d["reread_at"], d["reread_error"] = db.now(), None
    return d


def undo(conn, d):
    prev = d.get("before_reread")
    if not prev:
        return d, [{"ok": False, "text": "Nothing to undo"}]
    d["table"], d["verification"] = prev["table"], prev["verification"]
    d["before_reread"], d["reread_at"] = None, None
    documents.save(conn, d)
    return d, [{"ok": True, "text": "Put back the sheet from before the re-read"}]
