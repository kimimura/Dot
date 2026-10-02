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
    return rf"\d{{{c[4:]}}}" if c.startswith("INT:") else PATTERN[c]


def tidy_classes(p, widen=False):
    p = set(p)
    ints = {c for c in p if c.startswith("INT:")}
    if len(ints) > 1:
        p = (p - ints) | {"INT"}
    if widen and (ints or "INT" in p):
        p |= {"CODE"}
    return sorted(p)


def split_lines(texts):
    return [(p, line.split()) for p, t in enumerate(texts) for line in (t or "").splitlines() if line.split()]


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
    if "above" in rule:
        for L in range(1, len(lines)):
            if mask_line(lines[L - 1][1]) == rule["above"]:
                v = _take(lines[L][1], rule["s"], after, n)
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
            v = _take(toks, s, after, n)
            if v:
                out.append((L, " ".join(v)) if where else " ".join(v))
    return out
