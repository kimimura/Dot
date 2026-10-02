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
    return [dict(r) for r in conn.execute(
        f"SELECT TOP {int(limit)} p.name, p.times_used AS n, p.last_used_at FROM profiles p ORDER BY p.times_used DESC, p.name"
    ).fetchall()]


def uploads_by_day(conn, days):
    return [dict(r) for r in conn.execute(
        "SELECT LEFT(uploaded_at,10) AS day, COUNT(*) AS n FROM documents"
        " WHERE uploaded_at >= ? GROUP BY LEFT(uploaded_at,10) ORDER BY day", (db.days_ago(days),)).fetchall()]
