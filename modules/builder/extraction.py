from core import activity, db, jobs, pdftext
from core.ai.errors import LLMError
from modules.builder.review import ask_review
from modules.conversion import reading
from modules.documents import repository as documents, transcript
from modules.profiles import repository as profiles
from modules.reading import verify


def on_extract(conn, llm, d, pdf):
    prof = profiles.get(conn, d["profile_id"]) if d.get("profile_id") else None
    texts = pdftext.page_texts(pdf)
    activity.note(f"Profile Builder: reading {d['filename']}")
    # a known format is read by what it has learned first; a file that fits needs no model and teaches nothing new
    if prof and d["has_text_layer"]:
        table, ver, note = reading.read_direct(conn, d, prof, texts)
        if table:
            d["table"], d["signature"], d["extra_fields"], d["error"] = table, prof.get("signature") or {}, {}, None
            d["history"], d["verification"] = [], ver
            activity.note(f"Profile Builder: {d['filename']} read with the {prof['name']} format, no model: "
                          f"{activity.count(len(table['rows']), 'row')}, {activity.checked(ver)}")
            return _done(conn, d)
        activity.note(f"Profile Builder: {d['filename']} doesn't fully fit the {prof['name']} format ({note}), so it is read in its columns")
    try:
        table, sig, extra = reading.model_read(llm, d, pdf, prof, texts, hints=d.get("hints"), keep_new=True)
    except LLMError as e:
        d["stage"], d["error"] = "failed", str(e)
        activity.note(f"Profile Builder: {d['filename']} failed: {e}")
        transcript.bot(d, "failed", error=str(e))
        documents.save(conn, d)
        return d
    finally:
        jobs.progress.pop(d["id"], None)
    d["table"], d["signature"], d["extra_fields"], d["error"] = table, sig, extra, None
    d["history"] = []
    d["verification"] = verify.verify(table, "\n\n".join(texts), d["has_text_layer"])
    activity.note(f"Profile Builder: {d['filename']} read, {activity.count(len(table['rows']), 'row')}, {activity.checked(d['verification'])}")
    return _done(conn, d)


def _done(conn, d):
    ask_review(d, first=True)
    try:
        documents.save(conn, d)
    except Exception as e:
        # a long read can outlast the database connection; the result is handed back and saved on a fresh one
        if not db.lost(e):
            raise
        activity.note(f"Profile Builder: the database connection dropped during the read; saving {d['filename']} on a new one")
    return d
