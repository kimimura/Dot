from core import db
from modules.companion import dialogue


def add(d, who, text, **meta):
    entry = {"who": who, "text": text, "at": db.now()}
    entry.update(meta)
    d["transcript"].append(entry)
    return entry


def bot(d, key=None, text=None, **ctx):
    return add(d, "bot", text if text is not None else dialogue.say(key, **ctx))


def user(d, text, **meta):
    return add(d, "user", text, **meta)
