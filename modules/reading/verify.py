import re
from bisect import bisect_left, bisect_right
from collections import Counter
from statistics import median_low

import config


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


def verify(table, text, has_text_layer, edited=None, previous=None):
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
        ok -= _misplaced(table, text, cells)
    return {"cells": cells, "verified": ok, "total": total, "checked": has_text_layer}


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
        start = line_at[k] if k >= 0 else 0
        if k + 1 < len(rows_at):
            end = line_at[k + 1]
        elif k >= 0 and rows_at[k] == i:
            end = min(n_lines, line_at[k] + tail + 1)
        else:
            end = n_lines
        bands.append((starts[start], starts[end] if end < n_lines else len(flat)))
    return bands


def _misplaced(table, text, cells):
    flat, starts = flat_lines(text)
    bands = row_bands(table, flat, starts) if flat else None
    if not bands:
        return 0
    rcols = [c["name"] for c in table["columns"] if c.get("kind") != "doc"]
    per_doc = {}
    for r in table["rows"]:
        per_doc.setdefault(r.get("_doc", 0), []).append(r)
    # a value repeated on every row of its document is printed once for the whole document
    same = {(d, c) for d, rs in per_doc.items() for c in rcols if len({x.get(c, "") for x in rs}) == 1}
    moved = 0
    for i, r in enumerate(table["rows"]):
        a, b = bands[i]
        hay = flat[a:b]
        for c in rcols:
            key = f"{i}|{c}"
            if (r.get("_doc", 0), c) in same:
                continue
            if cells.get(key) == "ok" and not _found(r.get(c, ""), hay):
                cells[key] = "elsewhere"
                moved += 1
    return moved
