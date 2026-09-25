import os
import threading
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, abort, jsonify, render_template, request, send_file

load_dotenv(Path(__file__).resolve().parent / ".env")

from bot import db, dialogue, flow, history, llm as llm_mod, profiles  # noqa: E402
from bot.pdftext import PdfError  # noqa: E402

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0


@app.context_processor
def _assets():
    root = Path(app.static_folder)

    def asset(name):
        try:
            v = int(os.path.getmtime(root / name))
        except OSError:
            v = 0
        return f"/static/{name}?v={v}"
    return {"asset": asset}
_locks = defaultdict(threading.Lock)


class Busy(Exception):
    pass


def _lock(doc_id):
    lk = _locks[doc_id]
    if not lk.acquire(blocking=False):
        raise Busy()
    return lk


def _pdf_path(doc_id):
    return db.UPLOADS / f"{doc_id}.pdf"


def _doc_or_404(conn, doc_id):
    d = history.get(conn, doc_id)
    if not d:
        abort(404)
    return d


@app.errorhandler(404)
def _404(e):
    return jsonify(error="not found", say="I can't find that one."), 404


@app.errorhandler(413)
def _413(e):
    return jsonify(error="too large", say="That file is too big for me — 20 MB is my limit."), 413


@app.errorhandler(Busy)
def _busy(e):
    return jsonify(error="busy", say=dialogue.say("busy")), 409


@app.errorhandler(PdfError)
def _pdf(e):
    return jsonify(error="bad pdf", say=str(e)), 400


@app.errorhandler(Exception)
def _500(e):
    app.logger.exception("unhandled")
    return jsonify(error="server", say=f"Something broke on my side: {e.__class__.__name__}."), 500


# ── pages ────────────────────────────────────────────────────────────────────

@app.get("/")
def index():
    return render_template("index.html", name=dialogue.NAME)


@app.get("/api/health")
def health():
    return jsonify(llm=llm_mod.status(), name=dialogue.NAME)


# ── documents ────────────────────────────────────────────────────────────────

@app.post("/api/upload")
def upload():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify(error="no file", say="Drop a PDF and I'll get started."), 400
    if not f.filename.lower().endswith(".pdf"):
        return jsonify(error="not pdf", say="I only read PDFs."), 400
    tmp = db.UPLOADS / f"_incoming_{db.new_id()}.pdf"
    f.save(tmp)
    conn = db.connect()
    try:
        d = flow.on_upload(conn, tmp, f.filename)
        conn.commit()
        tmp.rename(_pdf_path(d["id"]))
        env = flow.envelope(conn, d)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    finally:
        conn.close()
    return jsonify(env)


@app.get("/api/docs")
def list_docs():
    conn = db.connect()
    out = history.list_docs(conn, q=request.args.get("q"), unfinished=request.args.get("unfinished") == "1")
    conn.close()
    return jsonify(docs=out)


@app.get("/api/docs/<doc_id>")
def get_doc(doc_id):
    conn = db.connect()
    d = _doc_or_404(conn, doc_id)
    env = flow.envelope(conn, d)
    conn.close()
    return jsonify(env)


@app.delete("/api/docs/<doc_id>")
def delete_doc(doc_id):
    conn = db.connect()
    d = _doc_or_404(conn, doc_id)
    history.delete(conn, doc_id)
    conn.commit()
    conn.close()
    for p in (_pdf_path(doc_id), d.get("xlsx_path"), d.get("csv_path")):
        if p:
            Path(p).unlink(missing_ok=True)
    return jsonify(ok=True)


def _run(doc_id, fn):
    lk = _lock(doc_id)
    try:
        conn = db.connect()
        try:
            d = _doc_or_404(conn, doc_id)
            result = fn(conn, d)
            conn.commit()
            changes = []
            if isinstance(result, tuple):
                d, changes = result
            else:
                d = result
            env = flow.envelope(conn, d, changes)
        finally:
            conn.close()
    finally:
        lk.release()
    return jsonify(env)


@app.post("/api/docs/<doc_id>/extract")
def extract_doc(doc_id):
    llm = llm_mod.get_llm()

    def fn(conn, d):
        if llm is None:
            d["stage"], d["error"] = "failed", "no API key configured"
            flow._bot(d, "failed", error="no API key is configured yet")
            history.save(conn, d)
            return d
        if d["stage"] != "extracting":
            return d
        return flow.on_extract(conn, llm, d, _pdf_path(doc_id))
    return _run(doc_id, fn)


@app.post("/api/docs/<doc_id>/answer")
def answer(doc_id):
    body = request.get_json(silent=True) or {}
    option = str(body.get("option") or "")
    if not option:
        return jsonify(error="no option", say="Pick one of the options."), 400
    return _run(doc_id, lambda conn, d: flow.on_answer(conn, llm_mod.get_llm(), d, option, body))


@app.post("/api/docs/<doc_id>/chat")
def chat(doc_id):
    body = request.get_json(silent=True) or {}
    msg = str(body.get("message") or "").strip()
    if not msg:
        return jsonify(error="empty", say="Say something and I'll help."), 400
    return _run(doc_id, lambda conn, d: flow.on_chat(conn, llm_mod.get_llm(), d, _pdf_path(doc_id), msg[:2000]))


@app.post("/api/docs/<doc_id>/ops")
def ops_route(doc_id):
    body = request.get_json(silent=True) or {}
    op_list = [o for o in (body.get("ops") or []) if isinstance(o, dict)]
    return _run(doc_id, lambda conn, d: flow.on_ops(conn, d, _pdf_path(doc_id), op_list))


@app.post("/api/docs/<doc_id>/undo")
def undo(doc_id):
    return _run(doc_id, lambda conn, d: flow.on_undo(conn, d, _pdf_path(doc_id)))


@app.post("/api/docs/<doc_id>/revise")
def revise(doc_id):
    return _run(doc_id, lambda conn, d: flow.revise(conn, d))


@app.get("/api/docs/<doc_id>/download.<ext>")
def download(doc_id, ext):
    conn = db.connect()
    d = _doc_or_404(conn, doc_id)
    conn.close()
    p = d.get("xlsx_path") if ext == "xlsx" else d.get("csv_path") if ext == "csv" else None
    if not p or not Path(p).exists():
        abort(404)
    base = Path(d["filename"]).stem
    return send_file(p, as_attachment=True, download_name=f"{base}.{ext}")


@app.get("/api/docs/<doc_id>/pdf")
def pdf(doc_id):
    p = _pdf_path(doc_id)
    if not p.exists():
        abort(404)
    return send_file(p, mimetype="application/pdf")


# ── profiles ─────────────────────────────────────────────────────────────────

def _profile_view(conn, p, with_docs=False):
    v = {k: p[k] for k in ("id", "name", "created_at", "updated_at", "columns", "hints", "signature", "times_used", "last_used_at")}
    v["core_tokens"] = profiles.core_tokens(p)
    v["n_docs"] = int((p.get("fingerprint") or {}).get("n_docs", 0))
    v["example"] = (p.get("examples") or [None])[0]
    if with_docs:
        v["documents"] = history.docs_for_profile(conn, p["id"])
    return v


@app.get("/api/profiles")
def list_profiles():
    conn = db.connect()
    out = [_profile_view(conn, p) for p in profiles.list_all(conn)]
    conn.close()
    return jsonify(profiles=out)


@app.get("/api/profiles/<pid>")
def get_profile(pid):
    conn = db.connect()
    p = profiles.get(conn, pid)
    if not p:
        conn.close()
        abort(404)
    v = _profile_view(conn, p, with_docs=True)
    conn.close()
    return jsonify(v)


@app.post("/api/profiles")
def create_profile():
    body = request.get_json(silent=True) or {}
    name = str(body.get("name") or "").strip()
    if not name:
        return jsonify(error="no name", say="Give the profile a name."), 400
    conn = db.connect()
    if profiles.by_name(conn, name):
        conn.close()
        return jsonify(error="exists", say=dialogue.say("name_taken", profile=name)), 409
    p = profiles.create(conn, name, body.get("columns") or [])
    conn.commit()
    v = _profile_view(conn, p)
    conn.close()
    return jsonify(v)


@app.put("/api/profiles/<pid>")
def update_profile(pid):
    body = request.get_json(silent=True) or {}
    conn = db.connect()
    p = profiles.get(conn, pid)
    if not p:
        conn.close()
        abort(404)
    if "name" in body:
        name = str(body["name"]).strip()
        other = profiles.by_name(conn, name)
        if not name or (other and other["id"] != pid):
            conn.close()
            return jsonify(error="name", say=dialogue.say("name_taken", profile=name) if name else "Give it a name."), 409
        p["name"] = name
    if "columns" in body and isinstance(body["columns"], list):
        cols, seen = [], set()
        for c in body["columns"]:
            n = str(c.get("name", "")).strip()[:60]
            if n and n.lower() not in seen:
                seen.add(n.lower())
                cols.append({"name": n, "kind": "doc" if c.get("kind") == "doc" else "row",
                             "hint": str(c.get("hint", "")).strip()[:200], "seen": int(c.get("seen", 0) or 0),
                             "aliases": [str(a).strip()[:60] for a in (c.get("aliases") or []) if str(a).strip()][:10]})
        p["columns"] = cols
    if "hints" in body and isinstance(body["hints"], list):
        p["hints"] = [{"text": str(h.get("text", "")).strip()[:300], "added_at": h.get("added_at") or db.now()}
                      for h in body["hints"] if str(h.get("text", "")).strip()]
    profiles.save(conn, p)
    conn.commit()
    v = _profile_view(conn, profiles.get(conn, pid), with_docs=True)
    conn.close()
    return jsonify(v)


@app.delete("/api/profiles/<pid>")
def delete_profile(pid):
    conn = db.connect()
    profiles.delete(conn, pid)
    conn.commit()
    conn.close()
    return jsonify(ok=True)


# ── stats ────────────────────────────────────────────────────────────────────

@app.get("/api/stats")
def stats():
    conn = db.connect()
    q = lambda sql, *a: conn.execute(sql, a).fetchone()[0]
    out = {
        "documents": q("SELECT COUNT(*) FROM documents"),
        "confirmed": q("SELECT COUNT(*) FROM documents WHERE stage='confirmed'"),
        "drafts": q("SELECT COUNT(*) FROM documents WHERE stage<>'confirmed'"),
        "profiles": q("SELECT COUNT(*) FROM profiles"),
        "rows": q("SELECT COALESCE(SUM(n_rows),0) FROM documents WHERE stage='confirmed'"),
        "this_week": q("SELECT COUNT(*) FROM documents WHERE uploaded_at >= datetime('now','-7 days','localtime')"),
        "verified_pct": q("SELECT ROUND(AVG(verified_pct),1) FROM documents WHERE verified_pct IS NOT NULL"),
        "recognized": q("SELECT COUNT(*) FROM documents WHERE stage='confirmed' AND profile_id IS NOT NULL"),
    }
    out["by_profile"] = [dict(r) for r in conn.execute(
        "SELECT p.name, p.times_used AS n, p.last_used_at FROM profiles p ORDER BY p.times_used DESC, p.name LIMIT 8").fetchall()]
    out["by_day"] = [dict(r) for r in conn.execute(
        "SELECT substr(uploaded_at,1,10) AS day, COUNT(*) AS n FROM documents"
        " WHERE uploaded_at >= datetime('now','-14 days','localtime') GROUP BY day ORDER BY day").fetchall()]
    conn.close()
    return jsonify(out)


if __name__ == "__main__":
    db.init_db()
    from waitress import serve
    port = int(os.environ.get("PORT", "5000"))
    print(f"{dialogue.NAME} is listening on http://127.0.0.1:{port}  (model: {llm_mod.status()})")
    serve(app, host="127.0.0.1", port=port, threads=4)
