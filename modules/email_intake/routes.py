from flask import Blueprint, jsonify, request

from modules.email_intake import service

bp = Blueprint("email_intake", __name__)


@bp.post("/api/email/intake")
def intake():
    service.check_token(request.headers.get("Token"))
    reply, status = service.receive(request.get_json(silent=True))
    return jsonify(reply), status
