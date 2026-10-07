import logging

from waitress import serve

import config
from core import ai, db


class BusyNote(logging.Filter):
    # the web server's own "Task queue depth is N" note, said in plain words
    def filter(self, record):
        waiting = record.args[0] if record.args else 0
        record.name = config.COMPANION_NAME
        record.msg, record.args = config.SERVER_BUSY_MESSAGE.format(threads=config.SERVER_THREADS, waiting=waiting,
                                                                    s="" if waiting == 1 else "s"), ()
        return True


def run(app, on_start=()):
    logging.getLogger("waitress.queue").addFilter(BusyNote())
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
    print(f"  model    {ai.status()}" + (f": {ai.models()}" if ai.models() else " - no models set (LLM_MODELS in .env)" if ai.status() != "offline" else ""))
    print(f"  database {db.where()} - {ready}")
    serve(app, host=config.HOST, port=config.PORT, threads=config.SERVER_THREADS)
