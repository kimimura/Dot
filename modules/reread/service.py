from flask import abort

from core import db, locks
from modules.conversion import queue as conversion, reread
from modules.documents import repository as documents, work
from modules.profiles import repository as profiles


def start(doc_id):
    env = work.run(doc_id, reread.start)
    if env["doc"]["stage"] == "rereading":
        conversion.enqueue(doc_id)
    return env


def undo(doc_id):
    return work.run(doc_id, reread.undo)


def start_profile(pid):
    conn = db.connect()
    try:
        if not profiles.get(conn, pid):
            abort(404)
        ids = documents.rereadable(conn, pid)
    finally:
        conn.close()
    started = []
    for did in ids:
        try:
            if work.run(did, reread.start)["doc"]["stage"] == "rereading":
                started.append(did)
        except locks.Busy:
            continue
    for did in started:
        conversion.enqueue(did)
    return len(started), len(ids) - len(started)
