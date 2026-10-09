import logging

from flask import Flask, jsonify

from core import activity, inflight, server


def queue_note(monkeypatch, waiting, working):
    lines = []
    monkeypatch.setattr(activity, "note", lines.append)
    monkeypatch.setattr(inflight, "snapshot", lambda: working)
    record = logging.LogRecord("waitress.queue", logging.WARNING, __file__, 1, "Task queue depth is %d", (waiting,), None)
    shown = server.BusyNote().filter(record)
    return shown, lines


def test_the_busy_note_is_a_plain_timed_line_listing_what_each_worker_is_doing(monkeypatch):
    shown, lines = queue_note(monkeypatch, 1, ["POST /api/docs/abc/chat  41.2s", "GET /api/docs  0.3s"])
    assert not shown and lines == ["Busy: all 4 workers are in use, 1 request waiting\n"
                                   "  1. POST /api/docs/abc/chat  41.2s\n  2. GET /api/docs  0.3s"]
    assert queue_note(monkeypatch, 3, ["GET /api/docs  0.3s"])[1][0].startswith("Busy: all 4 workers are in use, 3 requests waiting")


def test_a_page_loading_its_files_says_nothing(monkeypatch):
    assert queue_note(monkeypatch, 2, []) == (False, [])


def test_a_request_shows_while_it_is_being_answered_and_goes_once_done():
    app = Flask(__name__)
    inflight.track(app)

    @app.get("/api/slow")
    def slow():
        return jsonify(seen=inflight.snapshot())

    @app.get("/static/js/companion/robot.js")
    def robot():
        return jsonify(seen=inflight.snapshot())

    seen = app.test_client().get("/api/slow?x=1").get_json()["seen"]
    assert len(seen) == 1 and seen[0].startswith("GET /api/slow?x=1  ")
    assert app.test_client().get("/static/js/companion/robot.js").get_json()["seen"] == []
    assert inflight.snapshot() == []


def test_a_wrong_method_is_answered_plainly_and_not_logged_as_a_crash(client, caplog):
    r = client.get("/api/email/intake")
    assert r.status_code == 405 and r.get_json()["say"] == "405 Method Not Allowed."
    assert not [x for x in caplog.records if x.levelno >= logging.ERROR]
