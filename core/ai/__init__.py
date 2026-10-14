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


class ChatLane:
    # whatever a chat message or a sheet edit sets off is the chat models' work; the reading models only read a file at the start
    def __init__(self, llm):
        self.llm = llm

    def complete(self, pdf, prompt, kind="extract"):
        return self.llm.complete(pdf, prompt, kind="chat" if kind == "chat" else "chat_read")


def chat_lane(llm):
    return llm if llm is None or isinstance(llm, ChatLane) else ChatLane(llm)


def models():
    return ", ".join(config.AI_MODELS) if status() != "offline" else ""


def read_models():
    return ", ".join(config.AI_READ_MODELS) if status() != "offline" else ""
