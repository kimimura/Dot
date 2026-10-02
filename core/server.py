from waitress import serve

import config
from core import ai, db


def run(app, on_start=()):
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
    print(f"  model    {ai.status()}")
    print(f"  database {db.where()} - {ready}")
    serve(app, host=config.HOST, port=config.PORT, threads=config.SERVER_THREADS)
