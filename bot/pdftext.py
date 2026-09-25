import hashlib
import re
from dataclasses import dataclass, field

import pdfplumber

MAX_BYTES = 20 * 1024 * 1024
MAX_PAGES = 80
MAX_TOKENS = 150

STOP = set("""
the and for of to in on at by with from a an is are be as or this that these those it its
we you your our their they them he she his her was were will shall can may not no yes all
any each per via etc into over under after before between about above below than then
also only more most other some such same both either neither if so do does did done has
have had here there where when which who whom whose what why how one two three four five
six seven eight nine ten please thank thanks dear sir madam ref re
""".split())


class PdfError(Exception):
    pass


@dataclass
class PdfInfo:
    sha256: str
    size: int
    n_pages: int
    has_text_layer: bool
    text: str
    tokens: list = field(default_factory=list)
    structural: dict = field(default_factory=dict)


def _norm(word):
    w = re.sub(r"[^a-z]", "", word.lower())
    if len(w) < 3 or w in STOP or any(ch.isdigit() for ch in word):
        return None
    return w


def inspect(path):
    data = open(path, "rb").read()
    if not data.startswith(b"%PDF"):
        raise PdfError("That doesn't look like a PDF.")
    if len(data) > MAX_BYTES:
        raise PdfError(f"That file is over {MAX_BYTES // (1024 * 1024)} MB — too big for me.")
    sha = hashlib.sha256(data).hexdigest()
    try:
        pdf = pdfplumber.open(path)
    except Exception as e:
        raise PdfError(f"I couldn't open that PDF ({e.__class__.__name__}).")
    with pdf:
        n = len(pdf.pages)
        if n == 0:
            raise PdfError("That PDF has no pages.")
        if n > MAX_PAGES:
            raise PdfError(f"That PDF has {n} pages — I can handle up to {MAX_PAGES}.")
        pages = []
        for p in pdf.pages:
            try:
                pages.append(p.extract_text() or "")
            except Exception:
                pages.append("")
        text = "\n\n".join(pages)
        has_text = (sum(len(t.strip()) for t in pages) / n) >= 40
        p1 = pdf.pages[0]
        tokens, structural = [], {}
        if has_text:
            tokens = _fingerprint_tokens(p1)
        structural = {
            "size": _size_bucket(p1.width, p1.height),
            "landscape": p1.width > p1.height,
            "pages": "1" if n == 1 else ("2-5" if n <= 5 else "6+"),
        }
    return PdfInfo(sha, len(data), n, has_text, text, tokens, structural)


def _size_bucket(w, h):
    w, h = sorted((round(w), round(h)))
    if abs(w - 595) < 12 and abs(h - 842) < 12:
        return "A4"
    if abs(w - 612) < 12 and abs(h - 792) < 12:
        return "Letter"
    return "other"


def _fingerprint_tokens(page):
    h = page.height
    words = page.extract_words() or []
    picked = [w["text"] for w in words if w["top"] < h * 0.4 or w["top"] > h * 0.88]
    try:
        tables = page.extract_tables() or []
        if tables and tables[0]:
            picked += [c for c in tables[0][0] if c]
    except Exception:
        pass
    seen, out = set(), []
    for raw in picked:
        for part in re.split(r"[\s/|,;:()]+", str(raw)):
            t = _norm(part)
            if t and t not in seen:
                seen.add(t)
                out.append(t)
                if len(out) >= MAX_TOKENS:
                    return out
    return out


def text_of(path):
    try:
        with pdfplumber.open(path) as pdf:
            return "\n\n".join((p.extract_text() or "") for p in pdf.pages)
    except Exception:
        return ""
