from core import db


def _row_to_profile(r):
    return {
        "id": r["id"], "name": r["name"],
        "created_at": r["created_at"], "updated_at": r["updated_at"],
        "columns": db.loads(r["columns_json"], []),
        "fingerprint": db.loads(r["fingerprint_json"], {}),
        "hints": db.loads(r["hints_json"], []),
        "examples": db.loads(r["examples_json"], []),
        "signature": db.loads(r["signature_json"], {}),
        "times_used": r["times_used"], "last_used_at": r["last_used_at"],
        "layout": db.loads(r.get("layout_json"), None),
    }


def list_all(conn):
    rows = conn.execute("SELECT * FROM profiles ORDER BY name").fetchall()
    return [_row_to_profile(r) for r in rows]


def get(conn, pid):
    r = conn.execute("SELECT * FROM profiles WHERE id=?", (pid,)).fetchone()
    return _row_to_profile(r) if r else None


def by_name(conn, name):
    r = conn.execute("SELECT * FROM profiles WHERE LOWER(name)=LOWER(?)", (name,)).fetchone()
    return _row_to_profile(r) if r else None


def create(conn, name, columns=None, signature=None):
    pid = db.new_id()
    ts = db.now()
    conn.execute(
        "INSERT INTO profiles(id,name,created_at,updated_at,columns_json,fingerprint_json,signature_json)"
        " VALUES(?,?,?,?,?,?,?)",
        (pid, name.strip(), ts, ts, db.dumps(columns or []),
         db.dumps({"tokens": {}, "n_docs": 0, "structural": {}}), db.dumps(signature or {})),
    )
    return get(conn, pid)


def save(conn, p):
    conn.execute(
        "UPDATE profiles SET name=?, updated_at=?, columns_json=?, fingerprint_json=?, hints_json=?,"
        " examples_json=?, signature_json=?, times_used=?, last_used_at=?, layout_json=? WHERE id=?",
        (p["name"], db.now(), db.dumps(p["columns"]), db.dumps(p["fingerprint"]), db.dumps(p["hints"]),
         db.dumps(p["examples"]), db.dumps(p["signature"]), p["times_used"], p["last_used_at"],
         db.dumps(p.get("layout")), p["id"]),
    )


def delete(conn, pid):
    conn.execute("DELETE FROM profiles WHERE id=?", (pid,))
