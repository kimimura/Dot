import re
from difflib import SequenceMatcher

import config
from modules.reading.verify import norm_text


CLASSES = [("INT", r"\d+"), ("DEC", r"[-+]?[\d,]*\d\.\d+"), ("CODE", r"(?![-+]?[\d,]*\d\.\d+ )(?=\S*\d)[A-Za-z0-9][A-Za-z0-9\-/.]*"),
           ("WORD", r"[A-Za-z][A-Za-z.&'/-]*")]
PATTERN = {**dict(CLASSES), "ANY": r"\S+"}


def token_class(tok):
    for name, pat in CLASSES:
        if re.fullmatch(pat, tok):
            return f"INT:{len(tok)}" if name == "INT" else name
    return "ANY"


def class_pattern(c):
    if c.startswith("INT:"):
        return rf"\d{{{c[4:].replace('-', ',')}}}"
    return PATTERN[c]


def tidy_classes(p, widen=False):
    p = set(p)
    ints = {c for c in p if c.startswith("INT:")}
    if len(ints) > 1:
        p = (p - ints) | {"INT"}
    if widen and (ints or "INT" in p):
        p |= {"CODE"}
    return sorted(p)


class Lines(list):
    # the text's lines as (page, words), also knowing where each word starts and ends when the PDF said
    edges = None


def split_lines(texts):
    out = Lines((p, line.split()) for p, t in enumerate(texts) for line in (t or "").splitlines() if line.split())
    out.edges = line_edges(texts)
    return out


def line_edges(texts):
    # where each word of split_lines starts and ends across the page; None where the PDF didn't say
    out = []
    for t in texts:
        rows = [line.split() for line in (t or "").splitlines() if line.split()]
        known = getattr(t, "edges", None)
        if not known or len(known) != len(rows):
            known = [None] * len(rows)
        out += [e if e and len(e) == len(r) else [None] * len(r) for e, r in zip(known, rows)]
    return out


def line_middles(texts):
    return [[None if e is None else (e[0] + e[1]) / 2 for e in line] for line in line_edges(texts)]


def mask_token(tok):
    return "#" if any(ch.isdigit() for ch in tok) else tok


def mask_line(toks):
    return " ".join(mask_token(t) for t in toks)


def word_set(s):
    return {w for w in re.split(r"[^a-z0-9]+", (s or "").lower()) if w}


def join_tokens(toks, line_len, glue):
    out = toks[0][1]
    for (pl, _), (cl, t) in zip(toks, toks[1:]):
        out += t if glue and cl != pl and line_len[pl] == 1 else " " + t
    return out


def similar(a, b):
    return SequenceMatcher(None, norm_text(a), norm_text(b)).ratio() >= config.LAYOUT_SIMILAR


def _take(toks, s, after, n):
    if s > len(toks) - 1:
        return []
    if after == "$":
        return toks[s:]
    if after == "#":
        return toks[s:s + n] if s + n < len(toks) and mask_token(toks[s + n]) == "#" else []
    stop = next((j for j in range(s + 1, len(toks)) if toks[j] == after), None)
    return toks[s:stop] if stop else []


def wrapped(rule, lines, L, v):
    # a value running to the line end carries on to the next line when that line's first word could not have fitted
    # and is not how the part after the value opens
    box, edges = rule.get("wrap"), getattr(lines, "edges", None)
    if not box or not edges or not v:
        return v
    out, j = list(v), L
    while j + 1 < len(lines) and lines[j + 1][0] == lines[j][0]:
        cur, nxt = edges[j], edges[j + 1]
        if None in cur or None in nxt or abs(nxt[0][0] - box["left"]) > config.LAYOUT_WRAP_MARGIN:
            break
        space = min((b[0] - a[1] for a, b in zip(cur, cur[1:])), default=0)
        if cur[-1][1] + space + nxt[0][1] - nxt[0][0] <= box["right"] or mask_token(lines[j + 1][1][0]) in box["stops"]:
            break
        out += lines[j + 1][1]
        j += 1
    return out


def apply_rule(rule, lines, where=False):
    if "block" in rule:
        out = []
        for L in range(1, len(lines)):
            if mask_line(lines[L - 1][1]) == rule["block"]:
                part = []
                for j, pre in enumerate(rule["prefix"]):
                    if L + j >= len(lines):
                        break
                    toks = lines[L + j][1]
                    part += toks[len(pre):] if toks[:len(pre)] == pre else toks
                if part:
                    out.append((L, " ".join(part)) if where else " ".join(part))
        return out
    after, n, out = rule["after"], rule["n"], []
    if "under" in rule:
        for L in range(len(lines) - rule["skip"]):
            if mask_line(lines[L][1]) == rule["under"]:
                v = wrapped(rule, lines, L + rule["skip"], _take(lines[L + rule["skip"]][1], 0, after, n))
                if v:
                    out.append((L + rule["skip"], " ".join(v)) if where else " ".join(v))
        return out
    if "above" in rule:
        for L in range(1, len(lines)):
            if mask_line(lines[L - 1][1]) == rule["above"]:
                v = wrapped(rule, lines, L, _take(lines[L][1], rule["s"], after, n))
                if v:
                    out.append((L, " ".join(v)) if where else " ".join(v))
        return out
    ctx = rule["ctx"]
    anchored = ctx[0] == "^"
    c = ctx[1:] if anchored else ctx
    for L, (_, toks) in enumerate(lines):
        for s in ([len(c)] if anchored else range(len(c), len(toks))):
            if s > len(toks) - 1 or not all((x == "#" and mask_token(t) == "#") or x == t for x, t in zip(c, toks[s - len(c):s])):
                continue
            v = wrapped(rule, lines, L, _take(toks, s, after, n))
            if v:
                out.append((L, " ".join(v)) if where else " ".join(v))
    return out
