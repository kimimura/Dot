import json
from io import BytesIO
from pathlib import Path

from flask import abort

from core import db, sheets
from modules.documents import repository as documents, view, work
from modules.outputs import service as outputs
from modules.profiles import learning

MIMETYPES = {"csv": "text/csv", "json": "application/json", "pdf": "application/pdf"}


def list_docs(q, unfinished):
    conn = db.connect()
    out = documents.list_docs(conn, q=q, unfinished=unfinished)
    conn.close()
    return out


def envelope(doc_id):
    conn = db.connect()
    d = work.load_or_404(conn, doc_id)
    env = view.envelope(conn, d)
    conn.close()
    return env


def delete(doc_id):
    conn = db.connect()
    d = work.load_or_404(conn, doc_id)
    if d.get("profile_id"):
        learning.forget(conn, d["profile_id"], doc_id)
    documents.delete(conn, doc_id)
    conn.commit()
    conn.close()


def export(doc_id, ext):
    if ext not in ("csv", "json", "pdf"):
        abort(404)
    conn = db.connect()
    try:
        d = work.load_or_404(conn, doc_id)
        if ext == "pdf":
            body = documents.load_pdf(conn, doc_id)
        elif ext == "json":
            data = outputs.current(conn, d)
            body = data and json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        else:
            body = d.get("table") and sheets.csv_bytes(sheets.with_sender(d["table"], outputs.sender_of(conn, d))).getvalue()
    finally:
        conn.close()
    if not body:
        abort(404)
    return BytesIO(body), f"{Path(d['filename']).stem}.{ext}", MIMETYPES[ext]


def pdf_bytes(doc_id):
    conn = db.connect()
    try:
        data = documents.load_pdf(conn, doc_id)
    finally:
        conn.close()
    if not data:
        abort(404)
    return data
