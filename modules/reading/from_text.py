from difflib import SequenceMatcher

import config
from modules.reading import verify


def _pieces(ctx, i, row, c):
    # every run of words on the row's own lines, alone or carried on onto a later line no other cell holds
    s, e = ctx["own"][i]
    others = [verify.norm_text(str(v)) for k, v in row.items() if k != c]
    loose = [k for k in range(s, e) if ctx["plain"][k] and not any(ctx["plain"][k] in h for h in others if h)]
    for k in range(s, e):
        words = ctx["printed"][k].split()
        for a in range(len(words)):
            for b in range(a + 1, len(words) + 1):
                piece = " ".join(words[a:b])
                yield piece
                if b == len(words):
                    yield from (piece + " " + ctx["printed"][j] for j in loose if j > k)


def _best(ctx, i, row, c):
    value = str(row.get(c, "")).lower()
    held = {verify.norm_text(str(v)) for k, v in row.items() if k != c}
    scored = {}
    for piece in _pieces(ctx, i, row, c):
        m = SequenceMatcher(None, value, piece.lower())
        if m.real_quick_ratio() >= config.FIX_FROM_TEXT_SIMILAR and m.quick_ratio() >= config.FIX_FROM_TEXT_SIMILAR:
            score = m.ratio()
            if score >= config.FIX_FROM_TEXT_SIMILAR and verify.norm_text(piece) not in held:
                scored[piece] = score
    best = None
    for piece, score in sorted(scored.items(), key=lambda x: -x[1]):
        if best and score < best[1]:
            break
        if verify.fits(ctx, i, row, c, piece):
            # two different texts equally close to the cell: the PDF doesn't say which one it meant
            if best and verify.norm_text(piece) != verify.norm_text(best[0]):
                return None
            best = best or (piece, score)
    return best[0] if best else None


def _as_printed(ctx, i, row, c):
    # the same characters as the cell, spaced the way the PDF prints them
    value = str(row.get(c, ""))
    s, e = ctx["own"][i]
    if not value.strip() or any(" ".join(value.split()) in ctx["printed"][k] for k in range(s, e)):
        return None
    bare = "".join(value.split())
    found = {piece for piece in _pieces(ctx, i, row, c) if "".join(piece.split()) == bare}
    return found.pop() if len(found) == 1 else None


def fix(table, text, cells, cols, edited=(), learn_from=None):
    # a cell that doesn't match the PDF takes the closest text the PDF prints on that row, when exactly one fits
    ctx = verify.read_rows(table, text, learn_from)
    if not ctx:
        return table, 0
    rows, fixed = [dict(r) for r in table["rows"]], 0
    for key, state in cells.items():
        i, c = int(key.split("|", 1)[0]), key.split("|", 1)[1]
        if state not in ("miss", "ok") or c not in cols or key in edited or i >= len(rows) or not ctx["own"][i]:
            continue
        piece = _best(ctx, i, rows[i], c) if state == "miss" else _as_printed(ctx, i, rows[i], c)
        if piece and piece != rows[i][c]:
            rows[i][c], fixed = piece, fixed + 1
    return {**table, "rows": rows}, fixed
