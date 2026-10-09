RETRY_MARKERS = ("429", "500", "502", "503", "504", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "DEADLINE", "overloaded")
RATE_MARKERS = ("429", "resource_exhausted", "quota", "rate limit")
OVERLOAD_MARKERS = ("503", "unavailable", "overloaded", "high demand")

# what the user sees; deliberately says nothing about what is behind the companion
BUSY = "busy right now — try again later"
DAILY = "daily limit reached — try again tomorrow"
NO_MODEL = "no reading model is set up"
GARBLED = "unreadable result"
CUT_OFF = "reply was cut off before it finished"


class LLMError(Exception):
    pass


class Truncated(LLMError):
    pass


def friendly(e):
    m = str(e)
    low = m.lower()
    if "api_key_invalid" in low or "api key not valid" in low or "authentication" in low or "401" in m:
        return "service credentials rejected"
    if "perday" in low or "per day" in low:
        return DAILY
    if any(k.lower() in low for k in RETRY_MARKERS):
        return BUSY
    if "permission_denied" in low or "403" in m:
        return "request refused (permission denied)"
    if "404" in m or ("not found" in low and "model" in low):
        return "service misconfigured"
    return m[:180]
