import config
from core.ai.gemini import GeminiAdapter
from core.ai.offline import OfflineAdapter

OFFLINE = ("offline", "fake", "none")
_cache = {}


def status():
    if config.AI_PROVIDER.lower() in OFFLINE:
        return "offline"
    return "gemini" if config.AI_KEY else "offline"


def get_llm():
    if status() == "offline":
        return OfflineAdapter()
    key = (config.AI_KEY, config.AI_MODEL)
    if key not in _cache:
        _cache.clear()
        _cache[key] = GeminiAdapter(*key)
    return _cache[key]
