from flask import Blueprint, request

from modules.companion import dialogue

bp = Blueprint("companion", __name__)


@bp.before_app_request
def _persona():
    dialogue.set_persona(request.headers.get("X-Avatar", "classic"))
