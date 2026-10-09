import math

import config
from core import db


STATE_DEFAULTS = {
    "tokens": [], "structural": {}, "signature": {}, "table": None, "verification": None,
    "hints": [], "history": [], "transcript": [], "candidates": [], "pending_profile_id": None,
    "pending_name": None, "rejected_profile_ids": [], "extra_fields": {}, "duplicate_of": None, "pending": None,
    "reread_from": None, "reread_at": None, "reread_error": None, "before_reread": None,
}
# the conversation lives in its own table; everything else is kept in the document's saved state
STATE_KEYS = [k for k in STATE_DEFAULTS if k != "transcript"]
MESSAGE_FIELDS = ("who", "text", "at")
DOC_FIELDS = ("id, filename, sha256, size, n_pages, uploaded_at, confirmed_at, stage, error, profile_id, has_text_layer,"
              " n_rows, verified_pct, state_json, submission_id, position, auto_how, read_note")
UNFINISHED = ("identify", "pick", "extracting", "review", "revising", "confirm_ops", "save_ask", "naming", "pick_existing", "failed", "duplicate")


def _row_to_doc(r):
    st = db.loads(r["state_json"], {})
    d = {
        "id": r["id"], "filename": r["filename"], "sha256": r["sha256"], "size": r["size"],
        "n_pages": r["n_pages"], "uploaded_at": r["uploaded_at"], "confirmed_at": r["confirmed_at"],
        "stage": r["stage"], "error": r["error"], "profile_id": r["profile_id"],
        "has_text_layer": bool(r["has_text_layer"]), "n_rows": r["n_rows"], "verified_pct": r["verified_pct"],
        "submission_id": r.get("submission_id"), "position": r.get("position"), "auto_how": r.get("auto_how"),
        "read_note": r.get("read_note"),
    }
    for k, v in STATE_DEFAULTS.items():
        d[k] = st.get(k, [] if isinstance(v, list) else ({} if isinstance(v, dict) else v))
    return d


def create(conn, filename, info, submission_id, stage="identify", position=0):
    did = db.new_id()
    conn.execute(
        "INSERT INTO documents(id,filename,sha256,size,n_pages,uploaded_at,stage,has_text_layer,state_json,submission_id,position)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (did, filename, info.sha256, info.size, info.n_pages, db.now(), stage, int(info.has_text_layer),
         db.dumps({"tokens": info.tokens, "structural": info.structural}), submission_id, position),
    )
    return get(conn, did)


def _messages(conn, did):
    rows = conn.execute("SELECT who, text, created_at, meta_json FROM messages WHERE document_id=? ORDER BY seq", (did,)).fetchall()
    return [{"who": r["who"], "text": r["text"], "at": r["created_at"], **db.loads(r["meta_json"], {})} for r in rows]


def _save_messages(conn, did, transcript):
    conn.execute("DELETE FROM messages WHERE document_id=?", (did,))
    for seq, m in enumerate(transcript):
        meta = {k: v for k, v in m.items() if k not in MESSAGE_FIELDS}
        conn.execute("INSERT INTO messages(document_id,seq,who,text,created_at,meta_json) VALUES(?,?,?,?,?,?)",
                     (did, seq, m.get("who", ""), m.get("text"), m.get("at"), db.dumps(meta) if meta else None))


def _load(conn, r):
    if not r:
        return None
    d = _row_to_doc(r)
    d["transcript"] = _messages(conn, d["id"])
    return d


def get(conn, did):
    return _load(conn, conn.execute(f"SELECT {DOC_FIELDS} FROM documents WHERE id=?", (did,)).fetchone())


def by_sha(conn, sha, exclude=None):
    return _load(conn, conn.execute(f"SELECT TOP 1 {DOC_FIELDS} FROM documents WHERE sha256=? AND id<>? ORDER BY uploaded_at DESC",
                                    (sha, exclude or "")).fetchone())


def reusable(conn, sha, exclude=None):
    d = _load(conn, conn.execute(f"SELECT TOP 1 {DOC_FIELDS} FROM documents WHERE sha256=? AND id<>? AND stage IN ('confirmed','converted')"
                                 " ORDER BY CASE WHEN stage='confirmed' THEN 0 ELSE 1 END, uploaded_at DESC", (sha, exclude or "")).fetchone())
    return d if d and d.get("table") else None


def list_submission(conn, submission_id):
    rows = conn.execute(
        "SELECT d.id, d.filename, d.stage, d.error, d.n_pages, d.n_rows, d.verified_pct, d.has_text_layer, d.profile_id,"
        " d.auto_how, d.read_note, d.uploaded_at, p.name AS profile_name FROM documents d LEFT JOIN profiles p ON p.id=d.profile_id"
        " WHERE d.submission_id=? ORDER BY d.position, d.uploaded_at, d.filename", (submission_id,)).fetchall()
    return [dict(r) for r in rows]


def pending(conn):
    return [r["id"] for r in conn.execute("SELECT id FROM documents WHERE stage IN ('queued','converting','rereading')"
                                          " ORDER BY uploaded_at").fetchall()]


def rereadable(conn, pid):
    return [r["id"] for r in conn.execute("SELECT id FROM documents WHERE profile_id=? AND stage IN ('confirmed','converted')"
                                          " ORDER BY uploaded_at", (pid,)).fetchall()]


def save(conn, d):
    table = d.get("table")
    ver = d.get("verification") or {}
    n_rows = len(table["rows"]) if table else 0
    pct = math.floor(1000.0 * ver["verified"] / ver["total"]) / 10 if ver.get("checked") and ver.get("total") else None
    conn.execute(
        "UPDATE documents SET filename=?, stage=?, error=?, profile_id=?, confirmed_at=?, n_rows=?, verified_pct=?,"
        " auto_how=?, read_note=?, state_json=? WHERE id=?",
        (d["filename"], d["stage"], d.get("error"), d.get("profile_id"), d.get("confirmed_at"), n_rows, pct,
         d.get("auto_how"), d.get("read_note"), db.dumps({k: d.get(k) for k in STATE_KEYS}), d["id"]),
    )
    _save_messages(conn, d["id"], d.get("transcript") or [])


def delete(conn, did):
    conn.execute("DELETE FROM documents WHERE id=?", (did,))


def list_docs(conn, q=None, unfinished=False, limit=config.LIBRARY_LIST_LIMIT):
    sql = ("SELECT d.id, d.filename, d.uploaded_at, d.confirmed_at, d.stage, d.profile_id, d.n_pages, d.n_rows,"
           " d.verified_pct, d.has_text_layer, p.name AS profile_name, s.source, s.sender"
           " FROM documents d LEFT JOIN profiles p ON p.id=d.profile_id LEFT JOIN submissions s ON s.id=d.submission_id")
    where, args = [], []
    if q:
        where.append("(d.filename LIKE ? OR p.name LIKE ?)")
        args += [f"%{q}%", f"%{q}%"]
    if unfinished:
        where.append("d.stage IN (%s)" % ",".join("?" * len(UNFINISHED)))
        args += list(UNFINISHED)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY d.uploaded_at DESC OFFSET 0 ROWS FETCH NEXT ? ROWS ONLY"
    args.append(limit)
    out = []
    for r in conn.execute(sql, args).fetchall():
        d = dict(r)
        d["has_text_layer"] = bool(d["has_text_layer"])
        d["has_output"] = d["stage"] in ("confirmed", "converted", "rereading")
        out.append(d)
    return out


def docs_for_profile(conn, pid, limit=config.PROFILE_DOCS_SHOWN):
    rows = conn.execute("SELECT id, filename, uploaded_at, confirmed_at, n_rows FROM documents WHERE profile_id=?"
        " ORDER BY uploaded_at DESC OFFSET 0 ROWS FETCH NEXT ? ROWS ONLY", (pid, limit)).fetchall()
    return [dict(r) for r in rows]


def store_pdf(conn, doc_id, data):
    conn.write_blob("INSERT INTO document_files(pdf_data, document_id) VALUES(?, ?)", data, doc_id)


def load_pdf(conn, doc_id):
    r = conn.execute("SELECT pdf_data FROM document_files WHERE document_id=?", (doc_id,)).fetchone()
    return bytes(r["pdf_data"]) if r and r["pdf_data"] else None


