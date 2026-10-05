from core import db


def create(conn, rid, sender, stamp, doc_ids):
    conn.execute("INSERT INTO email_requests(id,sender,received_at,stamp,doc_ids_json,status) VALUES (?,?,?,?,?,?)",
                 (rid, sender, db.now(), stamp, db.dumps(doc_ids), "waiting"))


def get(conn, rid):
    r = conn.execute("SELECT id, sender, received_at, stamp, doc_ids_json, status, error, sent_at FROM email_requests WHERE id=?",
                     (rid,)).fetchone()
    if not r:
        return None
    req = dict(r)
    req["doc_ids"] = db.loads(req.pop("doc_ids_json"), [])
    return req


def waiting(conn):
    return [r["id"] for r in conn.execute("SELECT id FROM email_requests WHERE status='waiting' ORDER BY received_at").fetchall()]


def finish(conn, rid, status, error=None):
    conn.execute("UPDATE email_requests SET status=?, error=?, sent_at=? WHERE id=?", (status, error, db.now(), rid))
