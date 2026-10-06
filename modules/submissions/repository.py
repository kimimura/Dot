from core import db

FIELDS = "id, source, sender, received_at, stamp, status, error, sent_at"


def create(conn, sid, source, sender="", stamp=None, status=None):
    conn.execute("INSERT INTO submissions(id,source,sender,received_at,stamp,status) VALUES (?,?,?,?,?,?)",
                 (sid, source, sender, db.now(), stamp, status))


def get(conn, sid):
    r = conn.execute(f"SELECT {FIELDS} FROM submissions WHERE id=?", (sid,)).fetchone()
    return dict(r) if r else None


def waiting_emails(conn):
    return [r["id"] for r in conn.execute("SELECT id FROM submissions WHERE source='email' AND status='waiting'"
                                          " ORDER BY received_at").fetchall()]


def finish(conn, sid, status, error=None):
    conn.execute("UPDATE submissions SET status=?, error=?, sent_at=? WHERE id=?", (status, error, db.now(), sid))
