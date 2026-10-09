import logging

from waitress import serve

import config
from core import activity, ai, db, inflight


class BusyNote(logging.Filter):
    # the web server's own "Task queue depth is N" note, said in plain words; a page loading its files is not busy work
    def filter(self, record):
        lines = inflight.snapshot()
        if lines:
            waiting = record.args[0] if record.args else 0
            note = config.SERVER_BUSY_MESSAGE.format(threads=config.SERVER_THREADS, waiting=waiting, s="" if waiting == 1 else "s")
            activity.note(note + "".join(f"\n  {i}. {line}" for i, line in enumerate(lines, 1)))
        return False


def run(app, on_start=()):
    logging.basicConfig(format="%(asctime)s  %(message)s", datefmt=config.ACTIVITY_TIME_FORMAT, force=True)
    logging.getLogger("waitress.queue").addFilter(BusyNote())
    inflight.track(app)
    if not db.configured():
        raise SystemExit(
            "No database configured. Set these in .env:\n"
            "  DB_SERVER=host-or-ip\n"
            "  DB_NAME=database\n"
            "  DB_USER=user\n"
            "  DB_PASSWORD=secret")
    try:
        db.init_db()
        ready = "connected"
    except Exception as e:
        ready = f"UNREACHABLE ({str(e).strip()[:70]})"
        print("  the app will start, but nothing will work until the database is back")
    for fn in on_start:
        fn()
    print(f"{config.COMPANION_NAME} is listening on http://{config.HOST}:{config.PORT}")
    print(f"  chat     {ai.status()}" + (f": {ai.models()}" if ai.models() else " - no models set (LLM_MODELS in .env)" if ai.status() != "offline" else ""))
    if ai.read_models() and ai.read_models() != ai.models():
        print(f"  reading  {ai.status()}: {ai.read_models()}")
    print(f"  database {db.where()} - {ready}")
    serve(app, host=config.HOST, port=config.PORT, threads=config.SERVER_THREADS)
