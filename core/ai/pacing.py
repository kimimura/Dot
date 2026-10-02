import re
import threading
import time
from collections import deque

import config

_sent, _pace = deque(), threading.Lock()


def wait_turn():
    with _pace:
        while True:
            now = time.monotonic()
            while _sent and now - _sent[0] >= 60:
                _sent.popleft()
            if len(_sent) < config.AI_RPM:
                break
            time.sleep(60 - (now - _sent[0]) + 0.05)
        _sent.append(time.monotonic())


def retry_after(msg):
    m = re.search(r"retry in ([\d.]+)\s*s", msg, re.I) or re.search(r"retryDelay['\"]?\s*[:=]\s*['\"]?([\d.]+)s", msg)
    return float(m.group(1)) if m else None
