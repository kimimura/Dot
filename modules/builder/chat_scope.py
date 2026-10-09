import re

import config
from modules.reading.verify import norm_text

# what the chat model is shown: never the whole file, only the rows an instruction is about and the pages they are printed on
FLAGGED = ("miss", "elsewhere", "blank")
ROW_WORDS = re.compile(r"\b(?:rows?|lines?|baris)\s*#?\s*((?:\d+\s*(?:-|–|to|and|&|,|dan)?\s*)+)", re.I)


def mentioned(message, n):
    # rows the user names by number: "row 72", "rows 72 and 73", "lines 10-12"
    out = set()
    for m in ROW_WORDS.finditer(message or ""):
        nums = re.findall(r"\d+|-|–|to", m.group(1))
        prev = None
        for i, x in enumerate(nums):
            if x.isdigit():
                k = int(x)
                if prev is not None and i >= 2 and nums[i - 1] in ("-", "–", "to"):
                    out.update(range(prev, k + 1))
                out.add(k)
                prev = k
    return sorted(k - 1 for k in out if 1 <= k <= n)


def quoted(message, rows, cols):
    # rows holding a value the user typed, like a PO number or an item code
    words = {norm_text(w) for w in re.findall(r"[\w./&-]{4,}", message or "") if any(ch.isdigit() for ch in w)}
    words.discard("")
    hits = [i for i, r in enumerate(rows) if any(norm_text(r.get(c, "")) in words for c in cols)]
    return hits[:config.CHAT_QUOTED_ROWS]


def flagged(d):
    cells = (d.get("verification") or {}).get("cells", {})
    return sorted({int(k.split("|", 1)[0]) for k, v in cells.items() if v in FLAGGED})[:config.CHAT_FLAGGED_ROWS]


def page_of(row, cols, norm_pages):
    # the page a row is printed on: the first page holding its longest values
    for v in sorted((norm_text(row.get(c, "")) for c in cols), key=len, reverse=True)[:3]:
        if len(v) < 4:
            break
        for p, text in enumerate(norm_pages, 1):
            if v in text:
                return p
    return None


def pick(d, message, texts):
    t = d["table"]
    rows, cols = t["rows"], [c["name"] for c in t["columns"]]
    asked = mentioned(message, len(rows)) + quoted(message, rows, cols)
    marked = flagged(d)
    shown = sorted(set(range(min(config.CHAT_SAMPLE_ROWS, len(rows)))) | set(asked) | set(marked))
    norm_pages = [norm_text(x) for x in texts]
    pages = [1] if texts else []
    for i in asked + marked:
        p = page_of(rows[i], cols, norm_pages)
        if p and p not in pages:
            pages.append(p)
        if len(pages) >= config.CHAT_MAX_PAGES:
            break
    return shown, sorted(pages)
