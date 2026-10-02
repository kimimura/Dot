import contextvars
import queue
import threading
import traceback

_active = set()
_queued = set()
_guard = threading.Lock()
_q = queue.Queue()
_worker = {"thread": None}
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
        return key in _queued


def enqueue(key, fn):
    with _guard:
        if key in _queued:
            return False
        _queued.add(key)
        if not (_worker["thread"] and _worker["thread"].is_alive()):
            _worker["thread"] = threading.Thread(target=_drain, daemon=True, name="convert-queue")
            _worker["thread"].start()
    _q.put((key, contextvars.copy_context(), fn))
    return True


def _drain():
    while True:
        key, ctx, fn = _q.get()
        try:
            ctx.run(fn)
        except Exception:
            traceback.print_exc()
        finally:
            with _guard:
                _queued.discard(key)
