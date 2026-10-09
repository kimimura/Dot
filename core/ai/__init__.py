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
    key = (config.AI_KEY, tuple(config.AI_MODELS), tuple(config.AI_READ_MODELS))
    if key not in _cache:
        _cache.clear()
        _cache[key] = GeminiAdapter(*key)
    return _cache[key]


def models():
    return ", ".join(config.AI_MODELS) if status() != "offline" else ""


def read_models():
    return ", ".join(config.AI_READ_MODELS) if status() != "offline" else ""
