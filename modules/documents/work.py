import logging

from flask import abort

from core import db, locks
from modules.documents import repository as documents, view
from modules.outputs import service as outputs

log = logging.getLogger(__name__)


def load_or_404(conn, doc_id):
    d = documents.get(conn, doc_id)
    if not d:
        abort(404)
    return d


def run(doc_id, fn):
    lk = locks.take(doc_id)
    try:
        conn = db.connect()
        try:
            d = load_or_404(conn, doc_id)
            result = fn(conn, d)
            d, changes = result if isinstance(result, tuple) else (result, [])
            try:
                outputs.refresh(conn, d)
                conn.commit()
            except Exception:
                conn.close()
                conn = db.connect(tries=4)
                documents.save(conn, d)
                outputs.refresh(conn, d)
                conn.commit()
                log.warning("reconnected to save %s", doc_id)
            env = view.envelope(conn, d, changes)
        finally:
            conn.close()
    finally:
        lk.release()
    return env
