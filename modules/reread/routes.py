from flask import Blueprint, jsonify

from modules.reread import service

bp = Blueprint("reread", __name__)


@bp.post("/api/docs/<doc_id>/reread")
def reread_doc(doc_id):
    return jsonify(service.start(doc_id))


@bp.post("/api/docs/<doc_id>/reread/undo")
def undo_reread(doc_id):
    return jsonify(service.undo(doc_id))


@bp.post("/api/profiles/<pid>/reread")
def reread_profile(pid):
    started, skipped = service.start_profile(pid)
    return jsonify(started=started, skipped=skipped)
