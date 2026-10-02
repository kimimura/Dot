import logging

from core import ai, db, jobs, locks
from modules.builder import answers, chat, edits, extraction, identify
from modules.documents import repository as documents, service as document_service, transcript, view, work

log = logging.getLogger(__name__)


def upload(data, filename):
    conn = db.connect()
    try:
        d = identify.on_upload(conn, data, filename)
        documents.store_pdf(conn, d["id"], data)
        conn.commit()
        if d["stage"] == "extracting":
            kick(d["id"])
        env = view.envelope(conn, d)
    finally:
        conn.close()
    return env


def run(doc_id, fn):
    env = work.run(doc_id, fn)
    if env["doc"]["stage"] == "extracting":
        env["working"] = kick(doc_id) or jobs.running(doc_id)
    return env


def _read_fn(llm, doc_id):
    def fn(conn, d):
        if d["stage"] != "extracting":
            return d
        return extraction.on_extract(conn, llm, d, documents.load_pdf(conn, doc_id))
    return fn


def kick(doc_id):
    llm = ai.get_llm()

    def job():
        try:
            work.run(doc_id, _read_fn(llm, doc_id))
        except locks.Busy:
            pass
        except Exception:
            log.exception("reading %s failed", doc_id)
            _mark_failed(doc_id)
    return jobs.start(doc_id, job)


def _mark_failed(doc_id):
    try:
        conn = db.connect(tries=3)
        try:
            d = documents.get(conn, doc_id)
            if d and d["stage"] == "extracting":
                d["stage"], d["error"] = "failed", "stopped unexpectedly"
                transcript.bot(d, "failed", error="it stopped unexpectedly")
                documents.save(conn, d)
                conn.commit()
        finally:
            conn.close()
    except Exception:
        log.exception("could not mark %s failed", doc_id)


def extract(doc_id):
    kick(doc_id)
    return document_service.envelope(doc_id)


def review(doc_id):
    return run(doc_id, lambda conn, d: edits.adopt(conn, d))


def answer(doc_id, option, body):
    return run(doc_id, lambda conn, d: answers.on_answer(conn, ai.get_llm(), d, option, body))


def chat_message(doc_id, message):
    return run(doc_id, lambda conn, d: chat.on_chat(conn, ai.get_llm(), d, documents.load_pdf(conn, doc_id), message))


def apply_ops(doc_id, op_list):
    return run(doc_id, lambda conn, d: edits.on_ops(conn, d, documents.load_pdf(conn, doc_id), op_list))


def undo(doc_id):
    return run(doc_id, lambda conn, d: edits.on_undo(conn, d, documents.load_pdf(conn, doc_id)))


def revise(doc_id):
    return run(doc_id, lambda conn, d: edits.revise(conn, d))
