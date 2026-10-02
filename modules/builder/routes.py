from flask import Blueprint, jsonify, request

import config
from modules.builder import service

bp = Blueprint("builder", __name__)


@bp.post("/api/upload")
def upload():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify(error="no file", say="No file uploaded."), 400
    if not f.filename.lower().endswith(".pdf"):
        return jsonify(error="not pdf", say="Not a PDF."), 400
    return jsonify(service.upload(f.read(), f.filename))


@bp.post("/api/docs/<doc_id>/extract")
def extract(doc_id):
    return jsonify(service.extract(doc_id))


@bp.post("/api/docs/<doc_id>/review")
def review(doc_id):
    return jsonify(service.review(doc_id))


@bp.post("/api/docs/<doc_id>/answer")
def answer(doc_id):
    body = request.get_json(silent=True) or {}
    option = str(body.get("option") or "")
    if not option:
        return jsonify(error="no option", say="Pick one of the options."), 400
    return jsonify(service.answer(doc_id, option, body))


@bp.post("/api/docs/<doc_id>/chat")
def chat(doc_id):
    body = request.get_json(silent=True) or {}
    msg = str(body.get("message") or "").strip()
    if not msg:
        return jsonify(error="empty", say="Message is empty."), 400
    return jsonify(service.chat_message(doc_id, msg[:config.CHAT_MAX_CHARS]))


@bp.post("/api/docs/<doc_id>/ops")
def ops(doc_id):
    body = request.get_json(silent=True) or {}
    return jsonify(service.apply_ops(doc_id, [o for o in (body.get("ops") or []) if isinstance(o, dict)]))


@bp.post("/api/docs/<doc_id>/undo")
def undo(doc_id):
    return jsonify(service.undo(doc_id))


@bp.post("/api/docs/<doc_id>/revise")
def revise(doc_id):
    return jsonify(service.revise(doc_id))
