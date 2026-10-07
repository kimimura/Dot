import time

import config
from modules.outputs import build, repository
from modules.profiles import repository as profiles
from modules.submissions import repository as submissions

PROCESSED = ("converted", "confirmed")


def ready(d):
    return d.get("stage") in PROCESSED and bool(d.get("table"))


def of(conn, d):
    if not ready(d):
        return None
    # a file whose format isn't known yet still has an output, marked as unidentified
    p = profiles.get(conn, d["profile_id"]) if d.get("profile_id") else None
    chain = p["name"] if p else config.OUTPUT_UNIDENTIFIED
    return build.build(d["table"], chain, time.strftime(config.OUTPUT_TIME_FORMAT), sender_of(conn, d))


def sender_of(conn, d):
    s = submissions.get(conn, d["submission_id"]) if d.get("submission_id") else None
    return (s or {}).get("sender") or ""


def current(conn, d):
    # files read before outputs were kept have none stored, so theirs is worked out on the spot
    return repository.get(conn, d["id"], "current") or of(conn, d)


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
