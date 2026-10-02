from flask import Blueprint, jsonify, render_template

from core import ai, db
from modules.companion import dialogue
from modules.home import assets

bp = Blueprint("home", __name__)


@bp.app_context_processor
def _assets():
    return {"asset": assets.url}


@bp.get("/")
def index():
    return render_template("index.html", name=dialogue.NAME)


@bp.get("/api/health")
def health():
    return jsonify(llm=ai.status(), name=dialogue.NAME, db=db.probe())
