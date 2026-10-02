from flask import Blueprint, jsonify, request

from modules.profiles import service

bp = Blueprint("profiles", __name__)


@bp.get("/api/profiles")
def list_profiles():
    return jsonify(profiles=service.list_all())


@bp.get("/api/profiles/<pid>")
def get_profile(pid):
    return jsonify(service.get(pid))


@bp.post("/api/profiles")
def create_profile():
    body = request.get_json(silent=True) or {}
    return jsonify(service.create(body.get("name"), body.get("columns")))


@bp.put("/api/profiles/<pid>")
def update_profile(pid):
    return jsonify(service.update(pid, request.get_json(silent=True) or {}))


@bp.delete("/api/profiles/<pid>")
def delete_profile(pid):
    service.delete(pid)
    return jsonify(ok=True)
