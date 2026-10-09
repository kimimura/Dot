import logging

from core import activity, db, jobs, locks
from modules.conversion import convert, reread
from modules.documents import repository as documents
from modules.outputs import service as outputs

CONVERTING = ("queued", "converting")
log = logging.getLogger(__name__)


def enqueue(did):
    return jobs.enqueue(did, lambda: run(did))


def run(did):
    # emailed files and re-reads use only what each format has learned, so every file takes seconds and never waits on a model
    try:
        lk = locks.take(did)
    except locks.Busy:
        return
    try:
        conn = db.connect(tries=3)
        try:
            d = documents.get(conn, did)
            if d and d["stage"] == "rereading":
                _reread(conn, d)
            elif not d or d["stage"] not in CONVERTING:
                return
            else:
                d["stage"] = "converting"
                documents.save(conn, d)
                conn.commit()
                activity.note(f"Reading {d['filename']}")
                try:
                    convert.convert(conn, d, documents.load_pdf(conn, did))
                except Exception:
                    log.exception("converting %s failed", did)
                    d["stage"], d["error"] = "failed", "stopped unexpectedly"
                    activity.note(f"Failed: {d['filename']}: {d['error']}")
                # a layout the format learned while reading this file is kept, whatever became of the file
                try:
                    conn.commit()
                except Exception as e:
                    if not db.lost(e):
                        raise
                    activity.note(f"the database connection dropped while reading {d['filename']}; saving it on a new one")
        finally:
            conn.close()
        conn = db.connect(tries=4)
        try:
            documents.save(conn, d)
            outputs.refresh(conn, d)
            conn.commit()
        finally:
            conn.close()
    finally:
        jobs.progress.pop(did, None)
        lk.release()


def _reread(conn, d):
    try:
        reread.run(conn, d, documents.load_pdf(conn, d["id"]))
    except Exception:
        log.exception("re-reading %s failed", d["id"])
        d["reread_error"] = "stopped unexpectedly"
    d["stage"], d["reread_from"] = d.get("reread_from") or "converted", None


def resume_pending():
    try:
        conn = db.connect()
        try:
            for did in documents.pending(conn):
                enqueue(did)
        finally:
            conn.close()
    except Exception:
        pass
