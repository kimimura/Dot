import re
from bisect import bisect_left, bisect_right
from collections import Counter

import config
from modules.reading.layout_tokens import apply_rule, class_pattern, join_tokens, line_middles, mask_line, mask_token, split_lines


def seqs_of(col):
    return col.get("seqs") or {str(len(col["classes"])): col["classes"]}


def _piece(col):
    if col["var"]:
        return r"(?:\S+ )+?"
    alts = ["".join("(?:%s) " % "|".join(class_pattern(x) for x in pos) for pos in seq)
            for _, seq in sorted(seqs_of(col).items(), key=lambda kv: -int(kv[0]))]
    return "(?:" + "|".join(alts) + ")"


def _regex(spec, drop=None):
    out = ""
    for k, col in enumerate(spec):
        piece = f"(?P<c{k}>{_piece(col)})"
        out += f"(?:{piece})?" if col["optional"] or k == drop else piece
    return re.compile("^" + out + "$")


def _lead_regex(spec, n):
    return re.compile("^" + "".join(_piece(col) for col in spec[:n]))


def _noise_key(toks):
    # lines with words match with their numbers blanked out; number-only lines must repeat exactly
    return mask_line(toks) if any(mask_token(t) != "#" for t in toks) else " ".join(toks)


def _noise(lines):
    pages = {p for p, _ in lines}
    if len(pages) < 2:
        return set()
    seen = {}
    for p, toks in lines:
        seen.setdefault(_noise_key(toks), set()).add(p)
    return {k for k, ps in seen.items() if len(ps) == len(pages)}


def _header_change(variant, lines):
    for line in variant["header"]:
        want = [w for w in line.split() if mask_token(w) != "#"]
        if not want:
            continue
        best, score = None, 0.0
        for _, toks in lines:
            have = [t for t in toks if mask_token(t) != "#"]
            s = len(set(want) & set(have)) / max(len(set(want) | set(have)), 1)
            if s > score:
                best, score = have, s
        if not best or score < 0.5:
            return "header changed: table header not found"
        new = [t for t in best if t not in want]
        gone = [t for t in want if t not in best]
        if new:
            return f'header changed: new column "{" ".join(new)}"'
        if gone:
            return f'header changed: "{" ".join(gone)}" missing'
    return None


def _split(variant, texts):
    rule = variant["fields"].get(variant.get("split_by") or "")
    if not rule:
        return [texts]
    segs, cur = [], None
    for t in texts:
        got = apply_rule(rule, split_lines([t]))
        v = got[0] if got else None
        if v is not None and v != cur:
            segs.append([t])
            cur = v
        elif segs:
            segs[-1].append(t)
        else:
            segs.append([t])
    return segs


def read_variant(variant, texts):
    changed = _header_change(variant, split_lines(texts))
    if changed:
        return None, changed
    out = []
    for d, seg in enumerate(_split(variant, texts)):
        rows, why = _read_doc(variant, seg, many=bool(variant.get("split_by")))
        if rows is None:
            return None, why
        out += [{**r, "_doc": d} for r in rows]
    return out, None


def _read_doc(variant, texts, many=False):
    lines = split_lines(texts)
    if any(r.get("wrap") for r in variant["fields"].values()) and not any(e for line in lines.edges for e in line):
        return None, "layout needs word positions this file doesn't have"
    line_len = {i: len(toks) for i, (_, toks) in enumerate(lines)}
    doc = {}
    for c, rule in variant["fields"].items():
        if rule.get("empty"):
            doc[c] = ""
            continue
        got = apply_rule(rule, lines)
        if not got:
            return None, f'layout changed: "{c}" not found'
        if not many and rule.get("stable") and len(set(got)) > 1:
            return None, "layout changed: more than one document in the file"
        doc[c] = got[0]
    spec = variant["row"]
    span = variant.get("lead_lines", 1)
    row_re, lead_re = _regex(spec), _lead_regex(spec, variant["lead"])
    opens = [i for i in range(len(lines)) if lead_re.match(" ".join(t for j in range(i, min(i + span, len(lines))) for t in lines[j][1]) + " ")]
    if not opens:
        return None, "layout changed: no rows found"
    noise = _noise(lines)
    tail = next(((k, c["tail"]) for k, c in enumerate(spec) if c.get("tail")), None)
    tail_re = re.compile("|".join(class_pattern(x) for x in tail[1])) if tail else None

    middles = line_middles(texts)
    rows, failed, used = [], [], set()
    for k, start in enumerate(opens):
        stop = opens[k + 1] if k + 1 < len(opens) else len(lines)
        for m in range(span, min(stop - start, config.LAYOUT_MAX_ROW_LINES) + 1):
            toks = [(L, t) for L in range(start, start + m) for t in lines[L][1]]
            mt = row_re.match(" ".join(t for _, t in toks) + " ")
            if not mt:
                continue
            row, starts = _values(spec, mt, toks, line_len)
            off = _by_position(spec, row, starts, toks, [x for L in range(start, start + m) for x in middles[L]])
            if off:
                return None, off
            used.update(range(start, start + m))
            j, extra = start + m, []
            while tail and j < stop:
                if _noise_key(lines[j][1]) in noise:
                    j += 1
                    continue
                if len(lines[j][1]) <= config.LAYOUT_MAX_TAIL_TOKENS and all(tail_re.fullmatch(t) for t in lines[j][1]):
                    extra += lines[j][1]
                    used.add(j)
                    j += 1
                    continue
                break
            if extra:
                c = spec[tail[0]]["col"]
                row[c] = (row[c] + " " + " ".join(extra)).strip()
            rows.append(row)
            break
        else:
            failed.append((start, stop))

    if failed:
        return None, _row_problem(spec, failed, lines, len(opens))
    skip = set(variant.get("skip_lines") or ())
    stray = [L for L in range(opens[0], max(used) + 1) if L not in used and _noise_key(lines[L][1]) not in noise and mask_line(lines[L][1]) not in skip]
    if stray:
        return None, f"layout changed: {len(stray)} line{'' if len(stray) == 1 else 's'} between rows weren't understood"

    return [{**r, **doc} for r in rows], None


def _values(spec, mt, toks, line_len):
    offs, at = [], 0
    for _, t in toks:
        offs.append(at)
        at += len(t) + 1
    out, starts = {}, {}
    for k, col in enumerate(spec):
        a, b = mt.span(f"c{k}")
        if a < 0 or a == b:
            out[col["col"]] = ""
            continue
        starts[col["col"]] = bisect_left(offs, a)
        part = toks[starts[col["col"]]:bisect_right(offs, b - 1)]
        v = join_tokens(part, line_len, col.get("glue", False)) if col["var"] else " ".join(t for _, t in part)
        cut = col.get("cut") or {}
        if cut.get("prefix") and v.startswith(cut["prefix"]):
            v = v[len(cut["prefix"]):]
        if cut.get("suffix") and v.endswith(cut["suffix"]):
            v = v[:-len(cut["suffix"])]
        out[col["col"]] = v
    return out, starts


def _place_of(name, between, starts, toks, middles):
    # where a value sits between its two neighbouring columns on the same line: 0 at the one before, 1 at the one after
    if name not in starts or any(n not in starts for n in between):
        return None
    (b, a), c = (starts[n] for n in between), starts[name]
    if not toks[b][0] == toks[a][0] == toks[c][0] or None in (middles[b], middles[a], middles[c]) or middles[a] == middles[b]:
        return None
    return (middles[c] - middles[b]) / (middles[a] - middles[b])


def _by_position(spec, row, starts, toks, middles):
    # a value that could sit under either of two columns goes to the one it is printed beneath
    groups = {}
    for col in spec:
        if col.get("alt"):
            groups.setdefault(col["alt"], []).append(col)
    for group in groups.values():
        filled = [col for col in group if row[col["col"]]]
        if len(filled) != 1:
            continue
        place = _place_of(filled[0]["col"], filled[0]["between"], starts, toks, middles)
        if place is None:
            return "layout needs word positions this file doesn't have"
        home = min(group, key=lambda col: abs(col["spot"] - place))
        if home is not filled[0]:
            row[home["col"]], row[filled[0]["col"]] = row[filled[0]["col"]], ""
            starts[home["col"]] = starts.pop(filled[0]["col"])
    # a moved value shifts its neighbours' places too, so the one furthest from its own place is the one that moved
    off = {}
    for col in spec:
        if "spot" in col and row.get(col["col"]):
            place = _place_of(col["col"], col["between"], starts, toks, middles)
            if place is not None and abs(place - col["spot"]) > config.LAYOUT_SPOT_TOLERANCE:
                off[col["col"]] = abs(place - col["spot"])
    if off:
        return f'layout changed: "{max(off, key=off.get)}" printed under a different column'
    return None


def _row_problem(spec, failed, lines, total):
    blame = Counter()
    for start, stop in failed:
        for k, col in enumerate(spec):
            if col["var"] or col["optional"]:
                continue
            rx = _regex(spec, drop=k)
            if any(rx.match(" ".join(t for L in range(start, start + m) for t in lines[L][1]) + " ")
                   for m in range(1, min(stop - start, config.LAYOUT_MAX_ROW_LINES) + 1)):
                blame[col["col"]] += 1
                break
    if blame:
        c, n = blame.most_common(1)[0]
        return f'layout changed: "{c}" not found in {n} row{"" if n == 1 else "s"}'
    return f"layout changed: {len(failed)} of {total} rows didn't match"
