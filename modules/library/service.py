import config
from core import db
from modules.library import repository


def stats():
    conn = db.connect()
    out = repository.counts(conn, config.STATS_WEEK_DAYS)
    out["by_profile"] = repository.top_formats(conn, config.STATS_TOP_FORMATS)
    out["by_day"] = repository.uploads_by_day(conn, config.STATS_CHART_DAYS)
    conn.close()
    return out
