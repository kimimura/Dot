import math
from bisect import bisect_left
from difflib import SequenceMatcher
from statistics import median

import config
from modules.reading.layout_tokens import apply_rule, mask_line, mask_token, similar, word_set
from modules.reading import verify
from modules.reading.verify import norm_text


class Unlearnable(Exception):
    pass


def value_spans(value, toks):
    want, vt, out = norm_text(value), value.split(), []
    if not want:
        return out
    for s in range(len(toks)):
        if [t for _, t in toks[s:s + len(vt)]] == vt:
            out.append((s, s + len(vt)))
            continue
        if not norm_text(toks[s][1]):
            continue
        acc = ""
        for e in range(s, min(len(toks), s + 80)):
            acc += norm_text(toks[e][1])
            if acc == want:
                out.append((s, e + 1))
                break
            if not want.startswith(acc):
                break
    return out


def split_span(value, toks, taken, row_end):
    # a value whose last part spilled past the rest of its row, e.g. a description's code printed on the line after the amounts
    want = norm_text(value)
    for s in range(row_end):
        if s in taken or not norm_text(toks[s][1]):
            continue
        acc = ""
        for e in range(s, row_end):
            if e in taken:
                break
            acc += norm_text(toks[e][1])
            if not want.startswith(acc):
                break
            rest, acc2, f = want[len(acc):], "", row_end
            if not rest:
                break
            while f < len(toks) and len(acc2) < len(rest) and f - row_end < config.LAYOUT_MAX_TAIL_TOKENS:
                acc2 += norm_text(toks[f][1])
                f += 1
            if acc2 == rest:
                return (s, e + 1), (row_end, f)
    return None


def leftover_place(value, toks, where):
    # the one text column the model tidied (spaces, a fixed typo): it is whatever is left between the other columns
    spans = sorted(where.values())
    gaps = [(e1, s2) for (_, e1), (s2, _) in zip(spans, spans[1:]) if s2 > e1]
    if len(gaps) != 1:
        return None
    a, b = gaps[0]
    row_end = spans[-1][1]
    best = None
    for f in range(row_end, min(len(toks), row_end + config.LAYOUT_MAX_TAIL_TOKENS) + 1):
        text = " ".join(t for _, t in toks[a:b] + toks[row_end:f])
        score = SequenceMatcher(None, norm_text(text), norm_text(value)).ratio()
        if best is None or score > best[0]:
            best = (score, f)
    if best[0] < config.LAYOUT_SIMILAR:
        return None
    return (a, b), ((row_end, best[1]) if best[1] > row_end else None)


def table_bands(table, lines):
    text = "\n".join(" ".join(toks) for _, toks in lines)
    flat, starts = verify.flat_lines(text)
    bands = verify.row_bands(table, flat, starts)
    if not bands:
        raise Unlearnable("rows couldn't be located in the PDF text")
    out = [(bisect_left(starts, a), bisect_left(starts, b) if b < len(flat) else len(lines)) for a, b in bands]
    out[-1] = (out[-1][0], len(lines))
    return out


def join_pieces(table):
    # the model sometimes cuts one multi-page document into pieces; pieces sharing the document's id are one document
    first = {}
    for r in table["rows"]:
        first.setdefault(r.get("_doc", 0), r)
    dcols = [c["name"] for c in table["columns"] if c.get("kind") == "doc"]
    ids = [c for c in dcols if all(norm_text(r.get(c, "")) for r in first.values())]
    if len(first) < 2 or not ids:
        return table
    key = max(ids, key=lambda c: (len({norm_text(r[c]) for r in first.values()}), len(norm_text(next(iter(first.values()))[c]))))
    rows, doc, last = [], -1, None
    for r in table["rows"]:
        k = norm_text(r[key])
        if k != last:
            doc, last = doc + 1, k
        rows.append({**r, "_doc": doc})
    return {"columns": table["columns"], "rows": rows}


def doc_pages(table, texts):
    docs = {}
    for r in table["rows"]:
        docs.setdefault(r.get("_doc", 0), []).append(r)
    order = list(docs)
    if len(order) == 1:
        return [(docs[order[0]], list(range(len(texts))))]
    norm_pages = [norm_text(t) for t in texts]
    dcols = [c["name"] for c in table["columns"] if c.get("kind") == "doc"]
    ids = [c for c in dcols if len({norm_text(docs[d][0].get(c, "")) for d in order}) == len(order)
           and all(len(norm_text(docs[d][0].get(c, ""))) >= 4 for d in order)]
    for c in sorted(ids, key=lambda c: -len(norm_text(docs[order[0]][0][c]))):
        owner, cur, ok = [], order[0], True
        for p in range(len(texts)):
            hit = [d for d in order if norm_text(docs[d][0][c]) in norm_pages[p]]
            if len(hit) > 1:
                ok = False
                break
            cur = hit[0] if hit else cur
            owner.append(cur)
        if ok and [d for d in dict.fromkeys(owner)] == order:
            return [(docs[d], [p for p in range(len(texts)) if owner[p] == d]) for d in order]
    raise Unlearnable("couldn't tell the documents in the file apart")


def _with_wrap(rule, pairs):
    # a value that runs on to the next line somewhere: learn the box it is printed in and how the next part opens,
    # so a line is only joined when the word could not have fitted and does not open what follows
    if rule.get("after") != "$" or not all(getattr(ln, "edges", None) for ln, _ in pairs):
        return rule
    got = [((apply_rule(rule, ln, where=True) or [None])[0], ln, v) for ln, v in pairs]
    got = [(x[0], x[1], ln, v) for x, ln, v in got if x and ln.edges[x[0]] and None not in ln.edges[x[0]]]
    if not any(v != g and v.startswith(g + " ") for _, g, _, v in got):
        return rule
    left = median(ln.edges[L][0][0] for L, _, ln, _ in got)

    def boxed_lines(ln, L):
        return [j for j in range(L, min(L + config.LAYOUT_MAX_BLOCK_LINES, len(ln)))
                if ln[j][0] == ln[L][0] and ln.edges[j] and None not in ln.edges[j] and abs(ln.edges[j][0][0] - left) <= config.LAYOUT_WRAP_MARGIN]
    # the value's own lines and the line after it are in the box; what that line opens with marks where a value ends
    rights, stops = [], set()
    for L, _, ln, v in got:
        have = []
        for j in boxed_lines(ln, L):
            rights.append(ln.edges[j][-1][1])
            if len(have) >= len(v.split()):
                stops.add(mask_token(ln[j][1][0]))
                break
            have += ln[j][1]
    boxed = dict(rule, wrap={"left": round(left, 4), "right": round(max(rights), 4), "stops": sorted(stops)})
    before = [(apply_rule(rule, ln) or [None])[0] == v for ln, v in pairs]
    after = [(apply_rule(boxed, ln) or [None])[0] == v for ln, v in pairs]
    return boxed if sum(after) > sum(before) and all(a for a, b in zip(after, before) if b) else rule


def field_rule(name_words, pairs):
    # a few documents in a confirmed sheet may carry the model's mistakes: a rule must agree with nearly all of them
    need = max(1, math.ceil(config.LAYOUT_FIELD_TRUST * len(pairs)))
    for lines, value in pairs[:3]:
        vt = value.split()
        occs = []
        for L, (_, toks) in enumerate(lines):
            for s in range(len(toks) - len(vt) + 1):
                if toks[s:s + len(vt)] == vt:
                    label = []
                    for t in reversed(toks[max(0, s - 2):s]):
                        if mask_token(t) == "#":
                            break
                        label.insert(0, t)
                    lw = {w for t in label for w in word_set(t)}
                    occs.append((-(len(lw & name_words) - len(lw - name_words)), L, s))
        for below in (False, True):
            for _, L, s in sorted(occs):
                toks = lines[L][1]
                e = s + len(vt)
                after = "$" if e == len(toks) else mask_token(toks[e])
                if below:
                    if L == 0:
                        continue
                    rules = [{"above": mask_line(lines[L - 1][1]), "s": s, "after": after, "n": len(vt)}]
                else:
                    rules = [{"ctx": (["^"] if s - k < 0 else []) + [mask_token(t) for t in toks[max(0, s - k):s]], "after": after, "n": len(vt)}
                             for k in (1, 2, 3)]
                for rule in rules:
                    got = apply_rule(rule, lines, where=True)
                    if not got or got[0] != (L, value):
                        continue
                    rule = _with_wrap(rule, pairs)
                    if sum((apply_rule(rule, ln) or [None])[0] == v for ln, v in pairs) >= need:
                        return dict(rule, stable=len({v for _, v in got}) == 1)
    return _under_rule(pairs, need) or _block_rule(pairs, need)


def _under_rule(pairs, need):
    # a value opening its own line a few lines under a fixed label, e.g. a store name under "Deliver To"
    lines, value = pairs[0]
    vt = value.split()
    for L, (_, toks) in enumerate(lines):
        if toks[:len(vt)] != vt:
            continue
        after = "$" if len(vt) == len(toks) else mask_token(toks[len(vt)])
        for up in range(1, config.LAYOUT_MAX_BLOCK_LINES + 1):
            if L - up < 0 or not any(mask_token(t) != "#" for t in lines[L - up][1]):
                continue
            rule = {"under": mask_line(lines[L - up][1]), "skip": up, "after": after, "n": len(vt)}
            got = apply_rule(rule, lines, where=True)
            rule = _with_wrap(rule, pairs)
            if got and got[0] == (L, value) and sum((apply_rule(rule, ln) or [None])[0] == v for ln, v in pairs) >= need:
                return dict(rule, stable=len({v for _, v in got}) == 1)
    return None


def _block_rule(pairs, need):
    # a value printed over several lines under a label, sharing those lines with a block that is the same in every document
    lines, value = pairs[0]
    first = value.split()[:2]
    if len(first) < 2:
        return None
    at = next(((L, s) for L, (_, toks) in enumerate(lines) for s in range(len(toks) - 1) if toks[s:s + 2] == first and L > 0), None)
    if not at:
        return None
    label = mask_line(lines[at[0] - 1][1])
    starts = [next((L for L in range(1, len(ln)) if mask_line(ln[L - 1][1]) == label), None) for ln, _ in pairs]
    if None in starts:
        return None
    prefix = []
    for j in range(config.LAYOUT_MAX_BLOCK_LINES):
        rows = [ln[L + j][1] for (ln, _), L in zip(pairs, starts) if L + j < len(ln)]
        common = []
        for toks in zip(*rows):
            if len(set(toks)) > 1:
                break
            common.append(toks[0])
        prefix.append(common)
    best = None
    for k in range(1, config.LAYOUT_MAX_BLOCK_LINES + 1):
        rule = {"block": label, "prefix": prefix[:k], "k": k}
        agree = sum(similar((apply_rule(rule, ln) or [""])[0], v) for ln, v in pairs)
        if agree >= need and (best is None or agree > best[0]):
            best = (agree, rule)
    return best[1] if best else None
