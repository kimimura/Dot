from . import db

STATE_DEFAULTS = {
    "tokens": [], "structural": {}, "signature": {}, "table": None, "verification": None,
    "hints": [], "history": [], "transcript": [], "candidates": [], "pending_profile_id": None,
    "pending_name": None, "rejected_profile_ids": [], "extra_fields": {}, "duplicate_of": None, "pending": None,
}
STATE_KEYS = list(STATE_DEFAULTS)
MAX_UNDO = 10
UNFINISHED = ("identify", "pick", "extracting", "review", "revising", "confirm_ops", "save_ask", "naming", "pick_existing", "failed", "duplicate")


def _row_to_doc(r):
    st = db.loads(r["state_json"], {})
    d = {
        "id": r["id"], "filename": r["filename"], "sha256": r["sha256"], "size": r["size"],
        "n_pages": r["n_pages"], "uploaded_at": r["uploaded_at"], "confirmed_at": r["confirmed_at"],
        "stage": r["stage"], "error": r["error"], "profile_id": r["profile_id"],
        "has_text_layer": bool(r["has_text_layer"]), "n_rows": r["n_rows"], "verified_pct": r["verified_pct"],
        "xlsx_path": r["xlsx_path"], "csv_path": r["csv_path"],
    }
    for k, v in STATE_DEFAULTS.items():
        d[k] = st.get(k, [] if isinstance(v, list) else ({} if isinstance(v, dict) else v))
    return d


def create(conn, filename, info):
    did = db.new_id()
    conn.execute(
        "INSERT INTO documents(id,filename,sha256,size,n_pages,uploaded_at,stage,has_text_layer,state_json)"
        " VALUES(?,?,?,?,?,?,?,?,?)",
        (did, filename, info.sha256, info.size, info.n_pages, db.now(), "identify", int(info.has_text_layer),
         db.dumps({"tokens": info.tokens, "structural": info.structural})),
    )
    return get(conn, did)


def get(conn, did):
    r = conn.execute("SELECT * FROM documents WHERE id=?", (did,)).fetchone()
    return _row_to_doc(r) if r else None


def by_sha(conn, sha, exclude=None):
    r = conn.execute("SELECT * FROM documents WHERE sha256=? AND id<>? ORDER BY uploaded_at DESC LIMIT 1", (sha, exclude or "")).fetchone()
    return _row_to_doc(r) if r else None


def save(conn, d):
    table = d.get("table")
    ver = d.get("verification") or {}
    n_rows = len(table["rows"]) if table else 0
    pct = round(100.0 * ver["verified"] / ver["total"], 1) if ver.get("checked") and ver.get("total") else None
    conn.execute(
        "UPDATE documents SET filename=?, stage=?, error=?, profile_id=?, confirmed_at=?, n_rows=?, verified_pct=?,"
        " state_json=?, xlsx_path=?, csv_path=? WHERE id=?",
        (d["filename"], d["stage"], d.get("error"), d.get("profile_id"), d.get("confirmed_at"), n_rows, pct,
         db.dumps({k: d.get(k) for k in STATE_KEYS}), d.get("xlsx_path"), d.get("csv_path"), d["id"]),
    )


def delete(conn, did):
    conn.execute("DELETE FROM documents WHERE id=?", (did,))


def list_docs(conn, q=None, unfinished=False, limit=500):
    sql = ("SELECT d.id, d.filename, d.uploaded_at, d.confirmed_at, d.stage, d.profile_id, d.n_pages, d.n_rows,"
           " d.verified_pct, d.has_text_layer, d.xlsx_path, d.csv_path, p.name AS profile_name"
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
    sql += " ORDER BY d.uploaded_at DESC LIMIT ?"
    args.append(limit)
    out = []
    for r in conn.execute(sql, args).fetchall():
        d = dict(r)
        d["has_text_layer"] = bool(d["has_text_layer"])
        d["has_output"] = bool(d["xlsx_path"])
        out.append(d)
    return out


def docs_for_profile(conn, pid, limit=20):
    rows = conn.execute("SELECT id, filename, uploaded_at, confirmed_at, n_rows FROM documents WHERE profile_id=? ORDER BY uploaded_at DESC LIMIT ?", (pid, limit)).fetchall()
    return [dict(r) for r in rows]


def transcript_add(d, who, text, **meta):
    entry = {"who": who, "text": text, "at": db.now()}
    entry.update(meta)
    d["transcript"].append(entry)
    return entry


def snapshot(d):
    d["history"].append({"table": d["table"], "verification": d["verification"], "hints": list(d["hints"])})
    d["history"] = d["history"][-MAX_UNDO:]


def undo(d):
    if not d["history"]:
        return False
    s = d["history"].pop()
    d["table"], d["verification"], d["hints"] = s["table"], s["verification"], s["hints"]
    return True
