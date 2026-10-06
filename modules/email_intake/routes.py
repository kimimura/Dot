from flask import Blueprint, jsonify, request

from modules.email_intake import service

bp = Blueprint("email_intake", __name__)


@bp.post("/api/email/intake")
def intake():
    service.check_token(request.headers.get("Token"))
    body = request.get_json(silent=True)
    reply, status = service.receive(body if body is not None else service.loose_json(request.get_data(as_text=True)))
    return jsonify(reply), status
