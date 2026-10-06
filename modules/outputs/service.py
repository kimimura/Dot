import time

import config
from modules.outputs import build, repository
from modules.profiles import repository as profiles

PROCESSED = ("converted", "confirmed")


def of(conn, d):
    # only a processed file of a known format has an official output; an unidentified one waits until its format is taught
    if d.get("stage") not in PROCESSED or not d.get("table") or not d.get("profile_id"):
        return None
    p = profiles.get(conn, d["profile_id"])
    if not p:
        return None
    return build.build(d["table"], p["name"], p.get("date_order"), time.strftime(config.OUTPUT_TIME_FORMAT))


def refresh(conn, d):
    data = of(conn, d)
    if data:
        repository.save_current(conn, d["id"], data["chain"], data["process_date"], data)
    else:
        repository.clear_current(conn, d["id"])
    return data


def mark_sent(conn, d):
    data = refresh(conn, d)
    if data:
        repository.keep_sent(conn, d["id"], data["chain"], data["process_date"], data)
    return data
