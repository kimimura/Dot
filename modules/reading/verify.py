import re
from bisect import bisect_left, bisect_right
from collections import Counter
from statistics import median_low

import config
from modules.reading import doc_groups


def norm_text(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _chain(parts, hay, at):
    for p in parts[1:]:
        i = hay.find(p, at)
        if i < 0 or i - at > config.VERIFY_MAX_GAP:
            return False
        at = i + len(p)
    return True


def _found(value, hay):
    n = norm_text(value)
    if not n or len(n) <= 2 or n in hay:
        return True
    parts = [norm_text(p) for p in re.split(r"\s+", value.strip()) if norm_text(p)]
    if not parts:
        return True
    if len(parts) == 1:
        return parts[0] in hay
    at = 0
    for _ in range(config.VERIFY_MAX_ANCHORS):
        i = hay.find(parts[0], at)
        if i < 0:
            return False
        if _chain(parts, hay, i + len(parts[0])):
            return True
        at = i + 1
    return False


def verify(table, text, has_text_layer, edited=None, previous=None, learn_from=None):
    edited = edited or set()
    prev = (previous or {}).get("cells", {})
    cells, ok, total = {}, 0, 0
    hay = norm_text(text) if has_text_layer else ""
    seen = {}
    for r, row in enumerate(table["rows"]):
        for c in table["columns"]:
            key = f"{r}|{c['name']}"
            v = row.get(c["name"], "")
            if not v:
                cells[key] = "na"
                continue
            total += 1
            if key in edited or prev.get(key) == "edited":
                cells[key] = "edited"
                ok += 1
            elif not has_text_layer:
                cells[key] = "na"
            else:
                if v not in seen:
                    seen[v] = _found(v, hay)
                cells[key] = "ok" if seen[v] else "miss"
                ok += 1 if seen[v] else 0
    if has_text_layer:
        ok += _check_rows(table, text, cells, learn_from)
    total += _blank_document_fields(table, cells, edited | {k for k, v in prev.items() if v == "edited"})
    return {"cells": cells, "verified": ok, "total": total, "checked": has_text_layer}


def _blank_document_fields(table, cells, edited):
    # a value printed once per document belongs on every row of that document; a gap means a page was read on its own
    blanks, ids = 0, doc_groups.groups(table)
    for c in (c["name"] for c in table["columns"] if c.get("kind") == "doc"):
        filled = {g for r, g in zip(table["rows"], ids) if r.get(c)}
        for i, (r, g) in enumerate(zip(table["rows"], ids)):
            key = f"{i}|{c}"
            if not r.get(c) and g in filled and key not in edited:
                cells[key] = "blank"
                blanks += 1
    return blanks


def flat_lines(text):
    norm = [norm_text(line) for line in (text or "").splitlines()]
    starts, at = [], 0
    for n in norm:
        starts.append(at)
        at += len(n)
    return "".join(norm), starts


def _spot(value, flat):
    n = norm_text(value)
    i = flat.find(n)
    if i >= 0:
        return i, flat.find(n, i + 1) >= 0
    parts = [norm_text(p) for p in re.split(r"\s+", value.strip()) if norm_text(p)]
    hits, at = [], 0
    for _ in range(config.VERIFY_MAX_ANCHORS if len(parts) > 1 else 0):
        i = flat.find(parts[0], at)
        if i < 0 or len(hits) == 2:
            break
        if _chain(parts, flat, i + len(parts[0])):
            hits.append(i)
        at = i + 1
    return (hits[0] if hits else -1), len(hits) > 1


def _in_order(points):
    lines, idx, prev = [], [], [None] * len(points)
    for k, (_, line) in enumerate(points):
        j = bisect_left(lines, line)
        if j == len(lines):
            lines.append(line)
            idx.append(k)
        else:
            lines[j], idx[j] = line, k
        prev[k] = idx[j - 1] if j else None
    out, k = [], idx[-1] if idx else None
    while k is not None:
        out.append(points[k])
        k = prev[k]
    return out[::-1]


def row_bands(table, flat, starts):
    rcols = [c["name"] for c in table["columns"] if c.get("kind") != "doc"]
    owners = Counter(n for r in table["rows"] for n in {norm_text(r.get(c, "")) for c in rcols})
    spots, homes, seen_at = {}, [], {}
    for i, r in enumerate(table["rows"]):
        found = []
        for c in rcols:
            v = r.get(c, "")
            n = norm_text(v)
            if len(n) < config.VERIFY_MIN_ANCHOR or owners[n] > 1:
                continue
            if n not in spots:
                spots[n] = _spot(v, flat)
            pos, again = spots[n]
            if pos >= 0 and not again:
                found.append((bisect_right(starts, pos) - 1, c))
        if found:
            seen_at[i] = found
            homes.append((i, median_low([line for line, _ in found])))
    # where most of a row's values sit decides its place
    kept = _in_order(homes)
    # the column that usually opens a row (an item code, a line number...) marks where each row starts
    opens, prev = Counter(), -1
    for i, home in kept:
        top = min(line for line, _ in seen_at[i] if line > prev)
        opens.update({c for line, c in seen_at[i] if line == top})
        prev = home
    lead, hits = opens.most_common(1)[0] if opens else (None, 0)
    if hits * 2 < len(kept):
        lead = None
    anchors, prev = [], -1
    for i, home in kept:
        led = [line for line, c in seen_at[i] if c == lead and prev < line <= home]
        anchors.append((i, led[0] if led else min(line for line, _ in seen_at[i] if line > prev)))
        prev = home
    if not anchors:
        return None
    rows_at = [r for r, _ in anchors]
    line_at = [line for _, line in anchors]
    heights = [l2 - l1 for (r1, l1), (r2, l2) in zip(anchors, anchors[1:]) if r2 == r1 + 1]
    tail = min(config.VERIFY_MAX_TAIL_LINES, max(heights, default=6))
    n_lines = len(starts)
    bands = []
    for i in range(len(table["rows"])):
        k = bisect_right(rows_at, i) - 1
        if k >= 0 and rows_at[k] == i:
            above = line_at[k - 1] + 1 if k else 0
            below = line_at[k + 1] if k + 1 < len(rows_at) else min(n_lines, line_at[k] + tail + 1)
            closed = _closing_band(table, i, rcols, flat, starts, above, line_at[k], below)
            if closed:
                bands.append(closed)
                continue
        start = line_at[k] if k >= 0 else 0
        if k + 1 < len(rows_at):
            end = line_at[k + 1]
        elif k >= 0 and rows_at[k] == i:
            end = min(n_lines, line_at[k] + tail + 1)
        else:
            end = n_lines
        bands.append((starts[start], starts[end] if end < n_lines else len(flat)))
    return bands


def _closing_band(table, i, rcols, flat, starts, above, line, below):
    # an anchor can be a row's last line (a price line, say): the row then runs from its values above down to the next row
    pos = lambda n: starts[n] if n < len(starts) else len(flat)
    values = [norm_text(table["rows"][i].get(c, "")) for c in rcols]
    values = [v for v in values if len(v) >= config.VERIFY_MIN_ANCHOR]
    up = [p for p in (flat.rfind(v, pos(above), pos(line)) for v in values) if p >= 0]
    down = [p for p in (flat.find(v, pos(line + 1), pos(below)) for v in values) if p >= 0]
    if len(up) <= len(down):
        return None
    end = line + 1
    if i + 1 < len(table["rows"]):
        end = _next_row_line(table["rows"][i + 1], rcols, flat, starts, line + 1, below)
    return pos(bisect_right(starts, min(up)) - 1), pos(end)


def _next_row_line(row, rcols, flat, starts, first, last):
    pos = lambda n: starts[n] if n < len(starts) else len(flat)
    hits = [p for p in (flat.find(v, pos(first), pos(last)) for v in (norm_text(row.get(c, "")) for c in rcols)
                        if len(v) >= config.VERIFY_MIN_ANCHOR) if p >= 0]
    return bisect_right(starts, min(hits)) - 1 if hits else first


def strict_lines(text):
    return [re.sub(r"\s+", "", line.lower()) for line in (text or "").splitlines()]


def printed(value, lines, plain=None, begins=None):
    # exact match, spaces aside: the sheet may leave out separators the PDF prints but never adds or changes characters
    chars = re.sub(r"\s+", "", (value or "").lower())
    plain = [norm_text(line) for line in lines] if plain is None else plain
    want, begins = norm_text(chars), len(lines) if begins is None else begins
    if len(want) <= 2 or any(want in have and _fits(chars, line, False, False) for line, have in zip(lines[:begins], plain)):
        return True
    return _runs_on(chars, lines, plain, False, 0, begins)


def _fits(piece, line, start, end):
    skip = "[^a-z0-9]*"
    body = skip.join(re.escape(ch) for ch in piece)
    return re.search(("\\A" if start else "") + skip + body + skip + ("\\Z" if end else ""), line) is not None


def _runs_on(chars, lines, plain, at_start, first, begins=None):
    # a value may carry on at the start of a later line: a code wrapped under a description, or onto the next page
    want = norm_text(chars)
    after = [k + 1 for k, ch in enumerate(chars) if "a" <= ch <= "z" or "0" <= ch <= "9"]
    last = min(len(lines), first + config.VERIFY_WRAP_REACH) if at_start else min(len(lines), begins)
    for i in range(first, last):
        have = plain[i]
        if not have:
            continue
        if at_start and have.startswith(want) and _fits(chars, lines[i], True, False):
            return True
        cuts = [len(have)] if at_start else [m for m in range(1, len(want)) if want[m - 1] == have[-1]]
        for m in cuts:
            if m >= len(want) or not have.endswith(want[:m]):
                continue
            end = after[m - 1]
            nxt = next((k for k in range(end, len(chars)) if "a" <= chars[k] <= "z" or "0" <= chars[k] <= "9"), end)
            # a separator between the two parts, like the dash in "W20 - Black", may end this line or start the next
            for k in {end, nxt}:
                if _fits(chars[:k], lines[i], at_start, True) and _runs_on(chars[k:], lines, plain, True, i + 1):
                    return True
    return False


def _shape(s):
    return re.sub(r"[0-9]", "9", re.sub(r"[a-z]", "a", s))


def _own_lines(rows, rcols, plain):
    # a row's own lines run from the line holding its opening value (an item code, say) to the next row's opening line
    at = {}
    for k, n in enumerate(plain):
        at.setdefault(n, []).append(k)
    first = lambda r, c: norm_text((str(r.get(c, "")).split() or [""])[0])
    # the opening value (its first word) sits on a line of its own on the most rows, and tells rows apart
    alone = {c: sum(1 for r in rows if first(r, c) in at) for c in rcols}
    distinct = {c: len({first(r, c) for r in rows}) for c in rcols}
    alike = [c for c in rcols if 2 * alone[c] >= len(rows)]
    apart = [c for c in alike if 2 * distinct[c] >= max(distinct[x] for x in alike)]
    lead = max(apart, key=lambda c: (round(alone[c] / len(rows), 1), distinct[c], -rcols.index(c)), default=None)
    if not lead:
        return [None] * len(rows)
    opens = {first(r, lead) for r in rows} - {""}
    own, prev = [], -1
    # rows are printed in sheet order: each row opens at the next line holding its value
    for r in rows:
        hits = at.get(first(r, lead), [])
        k = bisect_right(hits, prev)
        if k == len(hits) or (prev >= 0 and hits[k] - prev > config.VERIFY_MAX_ROW_JUMP):
            own.append(None)
            continue
        prev = s = hits[k]
        reach = min(len(plain), s + config.VERIFY_MAX_ROW_JUMP)
        own.append((s, next((k for k in range(s + 1, reach) if plain[k] in opens), reach)))
    return own


def _wrap_shapes(rows, rcols, lines, plain, own):
    # learned from rows that kept them: the kind of line a column continues onto (a code printed under a long description)
    seen = {}
    for r, span in zip(rows, own):
        if not span:
            continue
        s, e = span
        mine = set(lines[s:e])
        for c in rcols:
            words = str(r.get(c, "")).lower().split()
            for k in range(1, len(words)):
                tail = "".join(words[k:])
                if tail in mine and printed(" ".join(words[:k]), lines[s:e], plain[s:e]):
                    seen.setdefault(c, Counter())[_shape(tail)] += 1
                    break
    return seen


def _rest_of_line(row, c, plain):
    # what follows the value on its line once the row's other values are taken off
    n = norm_text(row.get(c, ""))
    held = [norm_text(str(v)) for o, v in row.items() if o != c]
    # numbers printed side by side run together, so where one ends is only clear for values with words in them
    worded = len(n) >= config.VERIFY_MIN_ANCHOR and re.search("[a-z]", n)
    for have in plain if worded else []:
        i = have.find(n)
        if i >= 0:
            rest = have[i + len(n):]
            cut = True
            while rest and cut:
                cut = max((h for h in held if h and rest.startswith(h)), key=len, default="")
                rest = rest[len(cut):]
            return rest
    return None


def _line_end_columns(rows, rcols, plain, own):
    # columns whose values run to the end of their line on nearly every row
    rests = [{c: _rest_of_line(r, c, plain[span[0]:span[1]]) for c in rcols} if span else {} for r, span in zip(rows, own)]
    ends = set()
    for c in rcols:
        seen = [x[c] for x in rests if x.get(c) is not None]
        if len(seen) >= config.VERIFY_MIN_WRAPS and seen.count("") >= config.VERIFY_LINE_END_SHARE * len(seen):
            ends.add(c)
    return ends


def _cut_short(row, lines, plain, wraps):
    held = [norm_text(str(v)) for v in row.values()]
    short = set()
    for line, n in zip(lines, plain):
        if not n or any(n in h for h in held):
            continue
        best = max(wraps, key=lambda c: wraps[c][_shape(line)], default=None)
        if best and wraps[best][_shape(line)] >= config.VERIFY_MIN_WRAPS:
            short.add(best)
    return short


def read_rows(table, text, learn_from=None):
    # where each row sits in the PDF text, and what its columns usually look like there
    flat, starts = flat_lines(text)
    if not flat:
        return None
    lines = strict_lines(text)
    plain = [norm_text(line) for line in lines]
    rcols = [c["name"] for c in table["columns"] if c.get("kind") != "doc"]
    own = _own_lines(table["rows"], rcols, plain)
    pos = lambda n: starts[n] if n < len(starts) else len(flat)
    # when every value repeats somewhere, bands can't be placed: a row's own lines stand in for its band
    bands = row_bands(table, flat, starts) or [(pos(o[0]), pos(o[1])) if o else None for o in own]
    if not any(bands):
        return None
    spans = [(bisect_right(starts, b[0]) - 1, bisect_left(starts, b[1])) if b else None for b in bands]
    # another version of the same sheet (before a re-read, say) teaches what this one's columns usually look like
    more = list(zip(learn_from["rows"], _own_lines(learn_from["rows"], rcols, plain))) if learn_from else []
    seen_rows, seen_own = table["rows"] + [r for r, _ in more], own + [s for _, s in more]
    return {"flat": flat, "lines": lines, "plain": plain, "printed": [" ".join(x.split()) for x in text.splitlines()],
            "rcols": rcols, "own": own, "bands": bands, "spans": spans,
            "wraps": _wrap_shapes(seen_rows, rcols, lines, plain, seen_own), "ends": _line_end_columns(seen_rows, rcols, plain, seen_own)}


def _near(ctx, i):
    # exactness only needs the text near the row; where the row sits is judged by its band
    s, e = ctx["own"][i] or ctx["spans"][i]
    return slice(max(0, s - config.VERIFY_WRAP_REACH), e + (0 if ctx["own"][i] else config.VERIFY_WRAP_REACH))


def short_columns(ctx, i, row):
    # columns of the row that leave off part of what the PDF prints for it
    if not ctx["own"][i]:
        return set()
    s, e = ctx["own"][i]
    lines, plain = ctx["lines"][s:e], ctx["plain"][s:e]
    return _cut_short(row, lines, plain, ctx["wraps"]) | {c for c in ctx["ends"] if _rest_of_line(row, c, plain)}


def fits(ctx, i, row, c, value):
    near = _near(ctx, i)
    return printed(value, ctx["lines"][near], ctx["plain"][near]) and c not in short_columns(ctx, i, {**row, c: value})


def _check_rows(table, text, cells, learn_from=None):
    ctx = read_rows(table, text, learn_from)
    if not ctx:
        return 0
    flat, lines, plain = ctx["flat"], ctx["lines"], ctx["plain"]
    per_doc = {}
    for r in table["rows"]:
        per_doc.setdefault(r.get("_doc", 0), []).append(r)
    # a value repeated on every row of its document is printed once for the whole document
    same = {(d, c) for d, rs in per_doc.items() for c in ctx["rcols"] if len({x.get(c, "") for x in rs}) == 1}
    change = 0
    for i, r in enumerate(table["rows"]):
        if not ctx["bands"][i]:
            continue
        (a, b), (la, lb), near = ctx["bands"][i], ctx["spans"][i], _near(ctx, i)
        # a value that starts in the row's band may wrap past its end
        wrap = slice(la, lb + config.VERIFY_WRAP_REACH)
        for c in ctx["rcols"]:
            key, state, v = f"{i}|{c}", cells.get(f"{i}|{c}"), r.get(c, "")
            if state not in ("ok", "miss") or (r.get("_doc", 0), c) in same:
                continue
            if state == "ok" and not (_found(v, flat[a:b]) or printed(v, lines[wrap], plain[wrap], lb - la)):
                new = "elsewhere"
            elif printed(v, lines[near], plain[near]):
                new = "ok"
            else:
                new = "miss"
            change += (new == "ok") - (state == "ok")
            cells[key] = new
        for c in short_columns(ctx, i, r):
            if cells.get(f"{i}|{c}") == "ok":
                cells[f"{i}|{c}"] = "miss"
                change -= 1
    return change
