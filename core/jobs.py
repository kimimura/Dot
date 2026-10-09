import contextvars
import queue
import threading
import traceback

_active = set()
_queued = set()
_guard = threading.Lock()
# each lane works through its own line one job at a time, so slow jobs in one lane never hold up another
_lanes = {}
progress = {}


def running(key):
    with _guard:
        return key in _active


def start(key, fn):
    with _guard:
        if key in _active:
            return False
        _active.add(key)
    ctx = contextvars.copy_context()

    def run():
        try:
            ctx.run(fn)
        except Exception:
            traceback.print_exc()
        finally:
            with _guard:
                _active.discard(key)

    threading.Thread(target=run, daemon=True, name=f"job-{key}").start()
    return True


def queued(key):
    with _guard:
        return any(k == key for _, k in _queued)


def enqueue(key, fn, lane="convert"):
    with _guard:
        if (lane, key) in _queued:
            return False
        _queued.add((lane, key))
        line = _lanes.setdefault(lane, {"q": queue.Queue(), "thread": None})
        if not (line["thread"] and line["thread"].is_alive()):
            line["thread"] = threading.Thread(target=_drain, args=(lane,), daemon=True, name=f"{lane}-queue")
            line["thread"].start()
    line["q"].put((key, contextvars.copy_context(), fn))
    return True


def _drain(lane):
    q = _lanes[lane]["q"]
    while True:
        key, ctx, fn = q.get()
        try:
            ctx.run(fn)
        except Exception:
            traceback.print_exc()
        finally:
            with _guard:
                _queued.discard((lane, key))
