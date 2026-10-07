import hashlib
import io
import re
from dataclasses import dataclass, field

import pdfplumber
import pypdfium2 as pdfium
from pypdf import PdfReader, PdfWriter

import config

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


def inspect(data):
    if not data.startswith(b"%PDF"):
        raise PdfError("Not a PDF.")
    if len(data) > config.PDF_MAX_BYTES:
        raise PdfError(f"File is over {config.PDF_MAX_BYTES // (1024 * 1024)} MB.")
    sha = hashlib.sha256(data).hexdigest()
    try:
        pages = page_texts(data)
    except Exception as e:
        raise PdfError(f"PDF can't be opened ({e.__class__.__name__}).")
    n = len(pages)
    if n == 0:
        raise PdfError("PDF has no pages.")
    if n > config.PDF_MAX_PAGES:
        raise PdfError(f"PDF has {n} pages — {config.PDF_MAX_PAGES} max.")
    text = "\n\n".join(pages)
    has_text = (sum(len(t.strip()) for t in pages) / n) >= 40
    try:
        with pdfplumber.open(io.BytesIO(data), pages=[1]) as pdf:
            p1 = pdf.pages[0]
            tokens = _fingerprint_tokens(p1) if has_text else []
            w, h = p1.width, p1.height
    except Exception:
        tokens = _tokens_from_lines(pages[0]) if has_text else []
        w, h = _page_size(data)
    structural = {
        "size": _size_bucket(w, h),
        "landscape": w > h,
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
    return _tokenise(picked)


def _tokens_from_lines(text):
    lines = [l for l in text.splitlines() if l.strip()]
    n = len(lines)
    return _tokenise(lines[:max(1, round(n * 0.4))] + lines[int(n * 0.88):])


def _page_size(data):
    doc = pdfium.PdfDocument(data)
    try:
        return doc[0].get_size()
    finally:
        doc.close()


def _tokenise(picked):
    seen, out = set(), []
    for raw in picked:
        for part in re.split(r"[\s/|,;:()]+", str(raw)):
            t = _norm(part)
            if t and t not in seen:
                seen.add(t)
                out.append(t)
                if len(out) >= config.PDF_MAX_TOKENS:
                    return out
    return out


class PageText(str):
    # a page's text that also knows where each word starts and ends across the page, for telling columns and wrapped lines apart
    edges = None


def _spaced(tp, width):
    # some PDFs leave out the space between words: a gap between two letters' full widths marks one
    text = tp.get_text_range() or ""
    if len(text) != tp.count_chars():
        return text, None
    out, spans, prev = [], [], None
    for i, ch in enumerate(text):
        if ch in "\r\n" or ch.isspace():
            out.append(ch)
            spans.append(None)
            prev = None
            continue
        box = tp.get_charbox(i, loose=True)
        if prev:
            h = max(box[3] - box[1], prev[3] - prev[1], 1e-6)
            if box[0] - prev[2] > config.PDF_WORD_GAP * h and abs(box[1] - prev[1]) < h:
                out.append(" ")
                spans.append(None)
        out.append(ch)
        spans.append((box[0] / width, box[2] / width))
        prev = box
    return "".join(out), spans


def _word_edges(text, spans):
    # where each word starts and ends across the page (0 = left edge, 1 = right edge), line by line as the text splits into words
    lines, at = [], 0
    for line in text.splitlines(keepends=True):
        words = [(spans[at + m.start()][0], spans[at + m.end() - 1][1]) for m in re.finditer(r"\S+", line)
                 if spans[at + m.start()] and spans[at + m.end() - 1]]
        if line.split():
            lines.append(words if len(words) == len(line.split()) else None)
        at += len(line)
    return lines


def page_texts(data):
    doc = pdfium.PdfDocument(data)
    try:
        out = []
        for i in range(len(doc)):
            page = doc[i]
            tp = page.get_textpage()
            text, spans = _spaced(tp, page.get_width() or 1)
            page_text = PageText(text)
            page_text.edges = _word_edges(text, spans) if spans else None
            out.append(page_text)
            tp.close()
            page.close()
        return out
    finally:
        doc.close()


def page_count(data):
    return len(PdfReader(io.BytesIO(data)).pages)


def pages(data, first, last):
    reader = PdfReader(io.BytesIO(data))
    w = PdfWriter()
    for i in range(first - 1, last):
        w.add_page(reader.pages[i])
    out = io.BytesIO()
    w.write(out)
    return out.getvalue()


def text_of(data):
    if not data:
        return ""
    try:
        return "\n\n".join(page_texts(data))
    except Exception:
        return ""
