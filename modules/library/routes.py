from flask import Blueprint, jsonify

from modules.library import service

bp = Blueprint("library", __name__)


@bp.get("/api/stats")
def stats():
    return jsonify(service.stats())
