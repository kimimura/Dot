from flask import Blueprint, jsonify, request, send_file

from modules.upload import service

bp = Blueprint("upload", __name__)


@bp.post("/api/convert")
def convert_files():
    files = [f for f in request.files.getlist("file") if f and f.filename]
    if not files:
        return jsonify(error="no file", say="Send at least one PDF."), 400
    wait = request.args.get("wait") in ("1", "true", "yes")
    if wait and len(files) != 1:
        return jsonify(error="one file", say="With wait=1, send exactly one PDF."), 400
    bid, ids, rejected = service.accept([(f.filename, f.read()) for f in files], request.args.get("batch"))
    if wait:
        buf, name, headers = service.convert_now(ids, rejected)
        resp = send_file(buf, as_attachment=True, download_name=name, mimetype="text/csv")
        resp.headers.update(headers)
        return resp
    service.queue_all(ids)
    return jsonify(batch=bid, ids=ids, rejected=rejected)


@bp.get("/api/batches/<bid>")
def batch_status(bid):
    return jsonify(batch=bid, files=service.batch_status(bid))


@bp.get("/api/batches/<bid>/download.zip")
def batch_zip(bid):
    buf, name = service.batch_zip(bid)
    return send_file(buf, as_attachment=True, download_name=name, mimetype="application/zip")


@bp.post("/api/docs/<doc_id>/reconvert")
def reconvert(doc_id):
    service.retry(doc_id)
    return jsonify(ok=True)


@bp.post("/api/docs/<doc_id>/cancel")
def cancel(doc_id):
    service.cancel(doc_id)
    return jsonify(ok=True)
