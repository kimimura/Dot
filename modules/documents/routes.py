from io import BytesIO

from flask import Blueprint, jsonify, request, send_file

from modules.documents import service

bp = Blueprint("documents", __name__)


@bp.get("/api/docs")
def list_docs():
    return jsonify(docs=service.list_docs(request.args.get("q"), request.args.get("unfinished") == "1"))


@bp.get("/api/docs/<doc_id>")
def get_doc(doc_id):
    return jsonify(service.envelope(doc_id))


@bp.delete("/api/docs/<doc_id>")
def delete_doc(doc_id):
    service.delete(doc_id)
    return jsonify(ok=True)


@bp.get("/api/docs/<doc_id>/download.<ext>")
def download(doc_id, ext):
    buf, name, mimetype = service.export(doc_id, ext)
    return send_file(buf, as_attachment=True, download_name=name, mimetype=mimetype)


@bp.get("/api/docs/<doc_id>/pdf")
def pdf_view(doc_id):
    return send_file(BytesIO(service.pdf_bytes(doc_id)), mimetype="application/pdf")
