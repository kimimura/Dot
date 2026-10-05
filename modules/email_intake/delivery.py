import logging
import time

import config
from core import db, webhook
from modules.conversion import queue as conversion
from modules.documents import repository as documents
from modules.email_intake import message, repository

log = logging.getLogger(__name__)


def _finished(rid):
    conn = db.connect(tries=3)
    try:
        return not any(r["stage"] in conversion.CONVERTING for r in documents.list_batch(conn, rid))
    finally:
        conn.close()


def _results(req):
    conn = db.connect(tries=3)
    try:
        rows = documents.list_batch(conn, req["id"])
        for r in rows:
            r["table"] = (documents.get(conn, r["id"]) or {}).get("table") if r["stage"] == "converted" else None
    finally:
        conn.close()
    # listed in the order the email carried them
    order = {did: k for k, did in enumerate(req["doc_ids"])}
    return sorted(rows, key=lambda r: order.get(r["id"], len(order)))


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
        req = repository.get(conn, rid)
    finally:
        conn.close()
    if not req or req["status"] != "waiting":
        return
    deadline = time.time() + config.EMAIL_MAX_WAIT_SECONDS
    while not _finished(rid) and time.time() < deadline:
        time.sleep(config.EMAIL_POLL_SECONDS)
    status, error = _send(message.build(_results(req), req["stamp"], req["sender"]))
    conn = db.connect(tries=3)
    try:
        repository.finish(conn, rid, status, error)
        conn.commit()
    finally:
        conn.close()
