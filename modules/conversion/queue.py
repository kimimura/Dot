import logging
import threading

import config
from core import activity, db, jobs, locks
from modules.conversion import convert, reread
from modules.documents import repository as documents
from modules.outputs import service as outputs

CONVERTING = ("queued", "converting")
log = logging.getLogger(__name__)


def enqueue(did):
    return jobs.enqueue(did, lambda: run(did))


def _out_of_reach(e):
    return isinstance(e, db.Unreachable) or db.lost(e)


def run(did, tries=0):
    # emailed files and re-reads use only what each format has learned, so every file takes seconds and never waits on a model
    try:
        lk = locks.take(did)
    except locks.Busy:
        return
    try:
        _run(did)
    except Exception as e:
        # a database out of reach for a while is not the file's fault: it is read again once the database is back
        if not _out_of_reach(e) or tries >= config.QUEUE_DB_RETRIES:
            raise
        activity.note(f"Database out of reach while reading a file; trying again in {config.QUEUE_DB_RETRY_SECONDS} s")
        threading.Timer(config.QUEUE_DB_RETRY_SECONDS, lambda: jobs.enqueue(did, lambda: run(did, tries + 1))).start()
    finally:
        jobs.progress.pop(did, None)
        lk.release()


def _run(did):
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
            except Exception as e:
                if _out_of_reach(e):
                    raise
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


def _reread(conn, d):
    try:
        reread.run(conn, d, documents.load_pdf(conn, d["id"]))
    except Exception as e:
        if _out_of_reach(e):
            raise
        log.exception("re-reading %s failed", d["id"])
        d["reread_error"] = "stopped unexpectedly"
    d["stage"], d["reread_from"] = d.get("reread_from") or "converted", None


def resume_pending():
    # only the copy of Dot that takes email in picks up unfinished files, so two copies on one database never read the same file at once
    if not config.EMAIL_INTAKE_TOKEN:
        return
    try:
        conn = db.connect()
        try:
            for did in documents.pending(conn):
                enqueue(did)
        finally:
            conn.close()
    except Exception:
        pass
