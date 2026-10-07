import logging

from flask import Flask, jsonify

from core import inflight, server


def queue_note(waiting):
    record = logging.LogRecord("waitress.queue", logging.WARNING, __file__, 1, "Task queue depth is %d", (waiting,), None)
    server.BusyNote().filter(record)
    return record


def test_the_busy_note_is_said_in_plain_words(monkeypatch):
    monkeypatch.setattr(inflight, "snapshot", lambda: [])
    record = queue_note(1)
    assert record.name == "Dot" and record.getMessage() == "Busy: all 4 workers are in use, 1 request waiting"
    assert queue_note(3).getMessage() == "Busy: all 4 workers are in use, 3 requests waiting"


def test_the_busy_note_lists_what_each_worker_is_doing(monkeypatch):
    monkeypatch.setattr(inflight, "snapshot", lambda: ["POST /api/docs/abc/chat  41.2s", "GET /api/docs  0.3s"])
    assert queue_note(1).getMessage() == ("Busy: all 4 workers are in use, 1 request waiting\n"
                                          "  1. POST /api/docs/abc/chat  41.2s\n  2. GET /api/docs  0.3s")


def test_a_request_shows_while_it_is_being_answered_and_goes_once_done():
    app = Flask(__name__)
    inflight.track(app)

    @app.get("/api/slow")
    def slow():
        return jsonify(seen=inflight.snapshot())

    seen = app.test_client().get("/api/slow?x=1").get_json()["seen"]
    assert len(seen) == 1 and seen[0].startswith("GET /api/slow?x=1  ")
    assert inflight.snapshot() == []
