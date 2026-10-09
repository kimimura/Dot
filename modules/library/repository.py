from core import db

COUNTS = {
    "documents": "SELECT COUNT(*) FROM documents",
    "confirmed": "SELECT COUNT(*) FROM documents WHERE stage='confirmed'",
    "converted": "SELECT COUNT(*) FROM documents WHERE stage='converted'",
    "drafts": "SELECT COUNT(*) FROM documents WHERE stage NOT IN ('confirmed','converted')",
    "profiles": "SELECT COUNT(*) FROM profiles",
    "rows": "SELECT COALESCE(SUM(n_rows),0) FROM documents WHERE stage IN ('confirmed','converted')",
    "this_week": "SELECT COUNT(*) FROM documents WHERE uploaded_at >= ?",
    "verified_pct": "SELECT FLOOR(AVG(verified_pct) * 10) / 10 FROM documents WHERE verified_pct IS NOT NULL",
    "recognized": "SELECT COUNT(*) FROM documents WHERE stage='confirmed' AND profile_id IS NOT NULL",
}


def _one(conn, sql, *args):
    return list(conn.execute(sql, args).fetchone().values())[0]


def counts(conn, week_days):
    since = {"this_week": (db.days_ago(week_days),)}
    return {k: _one(conn, sql, *since.get(k, ())) for k, sql in COUNTS.items()}


def top_formats(conn, limit):
    # how many files each format was confirmed with is kept in its fingerprint
    rows = [{"name": r["name"], "n": int(db.loads(r["fingerprint_json"], {}).get("n_docs") or 0)}
            for r in conn.execute("SELECT name, fingerprint_json FROM profiles").fetchall()]
    return sorted(rows, key=lambda r: (-r["n"], r["name"]))[:int(limit)]


def uploads_by_day(conn, days):
    return [dict(r) for r in conn.execute(
        "SELECT LEFT(uploaded_at,10) AS day, COUNT(*) AS n FROM documents"
        " WHERE uploaded_at >= ? GROUP BY LEFT(uploaded_at,10) ORDER BY day", (db.days_ago(days),)).fetchall()]
