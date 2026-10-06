import io
import math
import zipfile
from pathlib import Path

from flask import abort

import config
from core import db, jobs, locks, sheets
from core.errors import Refused
from modules.conversion import intake, queue as conversion
from modules.documents import repository as documents, work
from modules.profiles import repository as profiles
from modules.submissions import repository as submissions

STARTED = "Already converting — can't remove it now."
CONVERTED_IN_BULK = ("upload", "email")


def _in_bulk(conn, d):
    s = submissions.get(conn, d.get("submission_id")) if d.get("submission_id") else None
    return bool(s) and s["source"] in CONVERTED_IN_BULK


def accept(files, batch_id):
    bid = batch_id or db.new_id()
    if not bid.isalnum() or len(bid) > config.BATCH_ID_MAX_CHARS:
        raise Refused(400, "bad batch", "That batch id isn't valid.")
    conn = db.connect()
    try:
        if not submissions.get(conn, bid):
            submissions.create(conn, bid, "upload")
        ids, rejected = intake.store(conn, files, bid)
        conn.commit()
    finally:
        conn.close()
    return bid, ids, rejected


def queue_all(ids):
    for did in ids:
        conversion.enqueue(did)


def convert_now(ids, rejected):
    if not ids:
        raise Refused(400, "bad pdf", rejected[0]["error"])
    conversion.run(ids[0])
    return csv_result(ids[0])


def csv_result(did):
    conn = db.connect()
    try:
        d = documents.get(conn, did)
        prof = profiles.get(conn, d["profile_id"]) if d and d.get("profile_id") else None
    finally:
        conn.close()
    if not d or d["stage"] != "converted":
        raise Refused(422, "failed", f"Conversion failed: {(d or {}).get('error') or 'unknown error'}.", id=did)
    ver = d.get("verification") or {}
    headers = {
        "X-Dot-Document": did,
        "X-Dot-Format": prof["name"] if prof else "",
        "X-Dot-Format-Chosen": d.get("auto_how") or "",
        "X-Dot-Rows": str(len(d["table"]["rows"])),
    }
    if ver.get("checked") and ver.get("total"):
        headers["X-Dot-Verified"] = f"{math.floor(1000.0 * ver['verified'] / ver['total']) / 10:.1f}"
    return sheets.csv_bytes(d["table"]), f"{Path(d['filename']).stem}.csv", headers


def batch_status(bid):
    conn = db.connect()
    try:
        files = documents.list_submission(conn, bid)
    finally:
        conn.close()
    for f in files:
        if f["stage"] in conversion.CONVERTING and not jobs.queued(f["id"]):
            conversion.enqueue(f["id"])
        f["progress"] = jobs.progress.get(f["id"])
        f["csv_url"] = f"/api/docs/{f['id']}/download.csv" if f["stage"] == "converted" else None
    return files


def batch_zip(bid):
    conn = db.connect()
    try:
        docs = [documents.get(conn, f["id"]) for f in documents.list_submission(conn, bid) if f["stage"] == "converted"]
    finally:
        conn.close()
    docs = [d for d in docs if d and d.get("table")]
    if not docs:
        abort(404)
    buf, used = io.BytesIO(), set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for d in docs:
            base = name = Path(d["filename"]).stem
            k = 2
            while name.lower() in used:
                name, k = f"{base} ({k})", k + 1
            used.add(name.lower())
            z.writestr(f"{name}.csv", sheets.csv_bytes(d["table"]).getvalue())
    buf.seek(0)
    return buf, f"dot-{bid}.zip"


def retry(doc_id):
    conn = db.connect()
    try:
        d = work.load_or_404(conn, doc_id)
        if d["stage"] != "failed" or not _in_bulk(conn, d):
            raise Refused(400, "not failed", "Only failed conversions can be retried.")
        d["stage"], d["error"] = "queued", None
        documents.save(conn, d)
        conn.commit()
    finally:
        conn.close()
    conversion.enqueue(doc_id)


def cancel(doc_id):
    try:
        lk = locks.take(doc_id)
    except locks.Busy:
        raise Refused(409, "started", STARTED)
    try:
        conn = db.connect()
        try:
            d = work.load_or_404(conn, doc_id)
            if d["stage"] not in ("queued", "failed") or not _in_bulk(conn, d):
                raise Refused(409, "started", STARTED)
            documents.delete(conn, doc_id)
            conn.commit()
        finally:
            conn.close()
    finally:
        lk.release()
