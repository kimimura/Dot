from pathlib import Path

from flask import abort

from core import db, sheets
from modules.documents import repository as documents, view, work
from modules.profiles import learning

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


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
    conn = db.connect()
    d = work.load_or_404(conn, doc_id)
    conn.close()
    if ext not in ("xlsx", "csv") or not d.get("table"):
        abort(404)
    base = Path(d["filename"]).stem
    buf = sheets.xlsx_bytes(d["table"], base) if ext == "xlsx" else sheets.csv_bytes(d["table"])
    return buf, f"{base}.{ext}", XLSX if ext == "xlsx" else "text/csv"


def pdf_bytes(doc_id):
    conn = db.connect()
    try:
        data = documents.load_pdf(conn, doc_id)
    finally:
        conn.close()
    if not data:
        abort(404)
    return data
