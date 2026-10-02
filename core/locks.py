import threading
from collections import defaultdict

_locks = defaultdict(threading.Lock)


class Busy(Exception):
    pass


def take(key):
    lk = _locks[key]
    if not lk.acquire(blocking=False):
        raise Busy()
    return lk
