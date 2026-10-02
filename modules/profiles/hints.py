import re

import config
from core import db


JUNK = ("uses columns", "columns:", "the columns are", "column list", "template uses",
        "following columns", "these columns", "column order is", "headers are")
ORDERING = re.compile(
    r"\b(place|put|move|position|insert|shift)\b.{0,80}?\b(before|after|first|last|front|end|start|beginning|left|right)\b"
    r"|\b(come|comes|go|goes|appear|appears|sit|sits)\s+(before|after|first|last)\b"
    r"|\b(first|last|leftmost|rightmost)\s+column\b|\bcolumn\s+(order|position)\b", re.I)


def about_order(text):
    return bool(ORDERING.search(text or ""))


def useful_hint(text, column_names=()):
    t = (text or "").strip()
    if not t or len(t) > config.PROFILE_HINT_MAX_CHARS:
        return False
    low = t.lower()
    if any(j in low for j in JUNK):
        return False
    hits = sum(1 for c in column_names if c and len(c) > 2 and c.lower() in low)
    return hits < 3


def merge_hints(existing, new, column_names=()):
    seen = {h["text"].strip().lower() for h in existing}
    out = [h for h in existing if useful_hint(h.get("text"), column_names)]
    for h in new:
        key = (h.get("text") or "").strip().lower()
        if key and key not in seen and useful_hint(h.get("text"), column_names) and not about_order(h.get("text")):
            out.insert(0, {"text": h["text"].strip(), "added_at": db.now()})
            seen.add(key)
    return out[:config.PROFILE_MAX_HINTS]
