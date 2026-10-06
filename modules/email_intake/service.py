import base64
import binascii
import hmac
import json
import time

import config
from core import db, jobs
from core.errors import Refused
from modules.conversion import intake, queue as conversion
from modules.email_intake import delivery
from modules.submissions import repository as submissions


def check_token(given):
    if not config.EMAIL_INTAKE_TOKEN or not hmac.compare_digest((given or "").strip(), config.EMAIL_INTAKE_TOKEN):
        raise Refused(403, "unauthorized", "Not allowed.")


def loose_json(text):
    # a mail flow pastes the email's preview in as-is, so its line breaks can arrive unescaped inside a string
    try:
        return json.loads(text, strict=False)
    except ValueError:
        return None


def _decode(content):
    if not isinstance(content, str) or not content:
        return b""
    if content.startswith("%PDF"):
        return content.encode("latin-1", "ignore")
    try:
        return base64.b64decode(content)
    except (binascii.Error, ValueError):
        return b""


def _watch(rid):
    jobs.start(f"email-{rid}", lambda: delivery.run(rid))


def receive(body):
    files = body.get("files") if isinstance(body, dict) else None
    if not isinstance(files, list) or not files:
        raise Refused(400, "no files", "No files were sent.")
    # the old intake sends filename/content, the mail service's own attachments use name/contentBytes
    pairs, skipped = [], []
    for f in (f if isinstance(f, dict) else {} for f in files):
        name, data = str(f.get("filename") or f.get("name") or "attachment"), _decode(f.get("content") or f.get("contentBytes"))
        if data:
            pairs.append((name, data))
        else:
            skipped.append({"file": name, "reason": "empty"})
    rid, stamp = db.new_id(), time.strftime(config.EMAIL_STAMP_FORMAT)
    conn = db.connect()
    try:
        submissions.create(conn, rid, "email", sender=str(body.get("email") or ""), stamp=stamp, status="waiting")
        ids, rejected = intake.store(conn, pairs, rid)
        if not ids:
            submissions.finish(conn, rid, "rejected", "no readable PDF")
        conn.commit()
    finally:
        conn.close()
    turned_away = {r["filename"] for r in rejected}
    skipped += [{"file": r["filename"], "reason": r["error"]} for r in rejected]
    if not ids:
        return {"status": "rejected", "count": 0, "files": [], "skipped": skipped}, 415
    for did in ids:
        conversion.enqueue(did)
    _watch(rid)
    return {"status": "accepted", "count": len(ids), "files": [n for n, _ in pairs if n not in turned_away], "skipped": skipped}, 200


def resume():
    # only the copy of Dot that takes email in sends results, so a second copy on the same database never sends twice
    if not config.EMAIL_INTAKE_TOKEN:
        return
    try:
        conn = db.connect()
        try:
            rids = submissions.waiting_emails(conn)
        finally:
            conn.close()
    except Exception:
        return
    for rid in rids:
        _watch(rid)
