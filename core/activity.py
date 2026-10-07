import math
import sys
import threading
import time

import config

_lock = threading.Lock()


def note(text):
    # one write per line, so lines from different threads never run into each other
    with _lock:
        sys.stdout.write(f"{time.strftime(config.ACTIVITY_TIME_FORMAT)}  {text}\n")
        sys.stdout.flush()


def checked(ver):
    if not (ver or {}).get("checked") or not ver.get("total"):
        return "not checked (scanned)"
    # rounded down, so 100% only when every value was found in the PDF
    return f"{math.floor(1000.0 * ver['verified'] / ver['total']) / 10:g}% checked"


def count(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"
