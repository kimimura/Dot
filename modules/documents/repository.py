import math

import config
from core import db


STATE_DEFAULTS = {
    "tokens": [], "structural": {}, "signature": {}, "table": None, "verification": None,
    "hints": [], "history": [], "transcript": [], "candidates": [], "pending_profile_id": None,
    "pending_name": None, "rejected_profile_ids": [], "extra_fields": {}, "duplicate_of": None, "pending": None,
    "reread_from": None, "reread_at": None, "reread_error": None, "before_reread": None,
}
STATE_KEYS = list(STATE_DEFAULTS)
UNFINISHED = ("identify", "pick", "extracting", "review", "revising", "confirm_ops", "save_ask", "naming", "pick_existing", "failed", "duplicate")


def _row_to_doc(r):
    st = db.loads(r["state_json"], {})
    d = {
        "id": r["id"], "filename": r["filename"], "sha256": r["sha256"], "size": r["size"],
        "n_pages": r["n_pages"], "uploaded_at": r["uploaded_at"], "confirmed_at": r["confirmed_at"],
        "stage": r["stage"], "error": r["error"], "profile_id": r["profile_id"],
        "has_text_layer": bool(r["has_text_layer"]), "n_rows": r["n_rows"], "verified_pct": r["verified_pct"],
        "batch_id": r.get("batch_id"), "auto_how": r.get("auto_how"), "read_note": r.get("read_note"),
    }
    for k, v in STATE_DEFAULTS.items():
        d[k] = st.get(k, [] if isinstance(v, list) else ({} if isinstance(v, dict) else v))
    return d


def create(conn, filename, info, batch_id=None, stage="identify"):
    did = db.new_id()
    conn.execute(
        "INSERT INTO documents(id,filename,sha256,size,n_pages,uploaded_at,stage,has_text_layer,state_json,batch_id)"
        " VALUES(?,?,?,?,?,?,?,?,?,?)",
        (did, filename, info.sha256, info.size, info.n_pages, db.now(), stage, int(info.has_text_layer),
         db.dumps({"tokens": info.tokens, "structural": info.structural}), batch_id),
    )
    return get(conn, did)


def get(conn, did):
    r = conn.execute("SELECT * FROM documents WHERE id=?", (did,)).fetchone()
    return _row_to_doc(r) if r else None


def by_sha(conn, sha, exclude=None):
    r = conn.execute("SELECT TOP 1 * FROM documents WHERE sha256=? AND id<>? ORDER BY uploaded_at DESC", (sha, exclude or "")).fetchone()
    return _row_to_doc(r) if r else None


def reusable(conn, sha, exclude=None):
    r = conn.execute("SELECT TOP 1 * FROM documents WHERE sha256=? AND id<>? AND stage IN ('confirmed','converted')"
                     " ORDER BY CASE WHEN stage='confirmed' THEN 0 ELSE 1 END, uploaded_at DESC", (sha, exclude or "")).fetchone()
    d = _row_to_doc(r) if r else None
    return d if d and d.get("table") else None


def list_batch(conn, batch_id):
    rows = conn.execute(
        "SELECT d.id, d.filename, d.stage, d.error, d.n_pages, d.n_rows, d.verified_pct, d.has_text_layer, d.profile_id,"
        " d.auto_how, d.read_note, d.uploaded_at, p.name AS profile_name FROM documents d LEFT JOIN profiles p ON p.id=d.profile_id"
        " WHERE d.batch_id=? ORDER BY d.uploaded_at, d.filename", (batch_id,)).fetchall()
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


def delete(conn, did):
    conn.execute("DELETE FROM documents WHERE id=?", (did,))


def list_docs(conn, q=None, unfinished=False, limit=config.LIBRARY_LIST_LIMIT):
    sql = ("SELECT d.id, d.filename, d.uploaded_at, d.confirmed_at, d.stage, d.profile_id, d.n_pages, d.n_rows,"
           " d.verified_pct, d.has_text_layer, p.name AS profile_name"
           " FROM documents d LEFT JOIN profiles p ON p.id=d.profile_id")
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
    conn.write_blob("UPDATE documents SET pdf_data=? WHERE id=?", data, doc_id)


def load_pdf(conn, doc_id):
    r = conn.execute("SELECT pdf_data FROM documents WHERE id=?", (doc_id,)).fetchone()
    return bytes(r["pdf_data"]) if r and r["pdf_data"] else None


def confirmed_ids(conn, pid, exclude):
    rows = conn.execute("SELECT id FROM documents WHERE profile_id=? AND stage='confirmed' AND id<>?", (pid, exclude)).fetchall()
    return [r["id"] for r in rows]
