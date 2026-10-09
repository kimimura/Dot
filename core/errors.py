from flask import jsonify, request
from werkzeug.exceptions import HTTPException

import config
from core.db import DbNotConfigured, Unreachable
from core.locks import Busy
from core.pdftext import PdfError


class Refused(Exception):
    def __init__(self, status, error, say, **extra):
        super().__init__(say)
        self.status, self.error, self.say, self.extra = status, error, say, extra


def register(app):
    @app.errorhandler(Refused)
    def _refused(e):
        return jsonify(error=e.error, say=e.say, **e.extra), e.status

    @app.errorhandler(404)
    def _404(e):
        return jsonify(error="not found", say="Not found."), 404

    @app.errorhandler(413)
    def _413(e):
        return jsonify(error="too large", say=f"File is over {config.PDF_MAX_BYTES // (1024 * 1024)} MB."), 413

    @app.errorhandler(Busy)
    def _busy(e):
        return jsonify(error="busy", say="Still processing this file — try again in a moment."), 409

    @app.errorhandler(DbNotConfigured)
    def _nodb(e):
        return jsonify(error="no database", say=f"Database not configured: {e}."), 503

    @app.errorhandler(Unreachable)
    def _unreachable(e):
        return jsonify(error="db unreachable", say="Database unreachable — try again in a moment."), 503

    @app.errorhandler(PdfError)
    def _pdf_error(e):
        return jsonify(error="bad pdf", say=str(e)), 400

    @app.errorhandler(HTTPException)
    def _http(e):
        # a wrong address or method is the caller's mistake, answered plainly rather than logged as a crash
        return jsonify(error=e.name.lower(), say=f"{e.code} {e.name}."), e.code

    @app.errorhandler(Exception)
    def _500(e):
        app.logger.exception(f"Error on {request.method} {request.path}")
        return jsonify(error="server", say=f"Server error ({e.__class__.__name__}) — try again."), 500
