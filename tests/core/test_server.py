import logging

from core import server


def queue_note(waiting):
    record = logging.LogRecord("waitress.queue", logging.WARNING, __file__, 1, "Task queue depth is %d", (waiting,), None)
    server.BusyNote().filter(record)
    return record


def test_the_busy_note_is_said_in_plain_words():
    record = queue_note(1)
    assert record.name == "Dot" and record.getMessage() == "Busy: all 4 workers are in use, 1 request waiting"
    assert queue_note(3).getMessage() == "Busy: all 4 workers are in use, 3 requests waiting"
