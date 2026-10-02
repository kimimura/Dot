import os

import config


def url(name):
    try:
        v = int(os.path.getmtime(config.STATIC_DIR / name))
    except OSError:
        v = 0
    return f"/static/{name}?v={v}"
