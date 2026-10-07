import logging
import time

import config
from core import activity, db, webhook
from modules.conversion import queue as conversion
from modules.documents import repository as documents
from modules.email_intake import message
from modules.outputs import service as outputs
from modules.submissions import repository as submissions

log = logging.getLogger(__name__)


def _finished(rid):
    conn = db.connect(tries=3)
    try:
        return not any(r["stage"] in conversion.CONVERTING for r in documents.list_submission(conn, rid))
    finally:
        conn.close()


def _results(rid):
    conn = db.connect(tries=3)
    try:
        rows = documents.list_submission(conn, rid)
        for r in rows:
            r["table"] = (documents.get(conn, r["id"]) or {}).get("table") if r["stage"] == "converted" else None
        return rows
    finally:
        conn.close()


def _send(payload):
    if not config.EMAIL_ALERT_URL:
        return "failed", "no alert address is set"
    error = None
    for attempt in range(config.EMAIL_ALERT_TRIES):
        if attempt:
            time.sleep(config.EMAIL_ALERT_RETRY_SECONDS)
        try:
            webhook.post_json(config.EMAIL_ALERT_URL, payload, config.EMAIL_ALERT_TIMEOUT)
            return "sent", None
        except webhook.WebhookError as e:
            error = str(e)
            log.warning("sending results failed, try %d of %d: %s", attempt + 1, config.EMAIL_ALERT_TRIES, e)
    return "failed", error


def run(rid):
    conn = db.connect(tries=3)
    try:
        req = submissions.get(conn, rid)
    finally:
        conn.close()
    if not req or req["source"] != "email" or req["status"] != "waiting":
        return
    deadline = time.time() + config.EMAIL_MAX_WAIT_SECONDS
    while not _finished(rid) and time.time() < deadline:
        time.sleep(config.EMAIL_POLL_SECONDS)
    docs = _results(rid)
    payload = message.build(docs, req["stamp"], req["sender"])
    status, error = _send(payload)
    activity.note(f'Reply sent to {req["sender"]}: "{payload["subject"]}"' if status == "sent" else f"Reply to {req['sender']} failed: {error}")
    conn = db.connect(tries=3)
    try:
        submissions.finish(conn, rid, status, error)
        if status == "sent":
            for r in docs:
                d = documents.get(conn, r["id"])
                if d:
                    outputs.mark_sent(conn, d)
        conn.commit()
    finally:
        conn.close()
