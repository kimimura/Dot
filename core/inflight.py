import threading
import time

from flask import request

_now, _guard = {}, threading.Lock()


def track(app):
    @app.before_request
    def started():
        # page files (styles, scripts, the companion) are not work worth reporting
        if request.path.startswith("/static/"):
            return
        with _guard:
            _now[threading.get_ident()] = (request.method, request.full_path.rstrip("?"), time.monotonic())

    @app.teardown_request
    def finished(_exc):
        with _guard:
            _now.pop(threading.get_ident(), None)


def snapshot():
    # the requests being answered right now, longest-running first
    t = time.monotonic()
    with _guard:
        busy = sorted(_now.values(), key=lambda x: x[2])
    return [f"{method} {path}  {t - start:.1f}s" for method, path, start in busy]
