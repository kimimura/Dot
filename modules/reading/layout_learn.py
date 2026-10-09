import re
from bisect import bisect_right
from collections import Counter
from statistics import median

import config
from modules.reading.layout_places import (Unlearnable, doc_pages, field_rule, join_pieces, leftover_place,
                                           split_span, table_bands, value_spans)
from modules.reading.layout_read import read_variant
from modules.reading.layout_tokens import (apply_rule, join_tokens, line_middles, mask_line, mask_token, similar, split_lines,
                                           tidy_classes, token_class, word_set)
from modules.reading.verify import norm_text


def _inside_word(value, toks, taken):
    # a value kept as only part of one printed word, e.g. 100028295 out of FC-100028295
    v = (value or "").strip()
    if len(v) < config.LAYOUT_MIN_CUT_VALUE or len(v.split()) != 1:
        return None
    for s, (_, t) in enumerate(toks):
        if s not in taken and len(t) > len(v):
            if t.endswith(v):
                return s, ("prefix", t[:-len(v)])
            if t.startswith(v):
                return s, ("suffix", t[len(v):])
    return None


def _place(r, toks, rcols):
    taken, where, tail, cut = set(), {}, {}, {}
    for c in sorted((c for c in rcols if r.get(c)), key=lambda c: (-len(norm_text(r[c])), rcols.index(c))):
        for s, e in value_spans(r[c], toks):
            if not taken.intersection(range(s, e)):
                where[c] = (s, e)
                taken.update(range(s, e))
                break
    for c in [c for c in rcols if r.get(c) and c not in where]:
        hit = _inside_word(r[c], toks, taken)
        if hit:
            where[c], cut[c] = (hit[0], hit[0] + 1), hit[1]
            taken.add(hit[0])
    missing = [c for c in rcols if r.get(c) and c not in where]
    if len(missing) == 1 and where:
        hit = leftover_place(r[missing[0]], toks, where)
        if hit:
            where[missing[0]], end = hit
            if end:
                tail[missing[0]] = end
            missing = []
    if missing and where:
        row_end = max(e for _, e in where.values())
        for c in missing:
            hit = split_span(r[c], toks, taken, row_end)
            if hit:
                where[c], tail[c] = hit
                taken.update(range(*hit[0]))
                break
    return where, tail, cut


def _gaps(where, tail, toks):
    # printed words in a row that belong to no column of the sheet (one the user dropped): kept as parts to skip, named by where they sit
    spans = sorted([(s, e, c) for c, (s, e) in where.items()] + [(s, e, f"{c} spill") for c, (s, e) in tail.items()])
    if not spans:
        return {}
    gaps, (first, _, name) = {}, spans[0]
    a = first
    while a > 0 and toks[a - 1][0] == toks[first][0]:
        a -= 1
    if a < first:
        gaps[f"_before {name}"] = (a, first)
    for (_, e1, c1), (s2, _, c2) in zip(spans, spans[1:]):
        # words between two columns of the row, or on one line; never the lines before text that spills on after the row
        if e1 < s2 and (toks[e1 - 1][0] == toks[s2][0] or not (c1.endswith(" spill") or c2.endswith(" spill"))):
            gaps[f"_after {c1}"] = (e1, s2)
    end, last = spans[-1][1], spans[-1][2]
    b = end
    while b < len(toks) and toks[b][0] == toks[end - 1][0]:
        b += 1
    if b > end:
        gaps[f"_after {last}"] = (end, b)
    return gaps


def _skip_lines(placed, one_page):
    # printed lines inside the rows that the confirmed sheet kept nothing from (e.g. "6 BOXES 5.00 4.21" under an item):
    # their shape, numbers masked, is skipped on new files; a line of numbers alone is never learned, so a lost row can't hide as one
    # the last row of each document runs into its footer, and a row across a page break holds the next page's header,
    # so only rows on one page with another row after them teach lines to skip
    last = {r.get("_doc", 0): i for i, (r, *_) in enumerate(placed)}
    shapes = set()
    for i, (r, toks, where, tail, _) in enumerate(placed):
        if last[r.get("_doc", 0)] == i or id(r) not in one_page:
            continue
        kept = {toks[k][0] for s, e in list(where.values()) + list(tail.values()) for k in range(s, e)}
        if not kept:
            continue
        by_line = {}
        for L, t in toks:
            by_line.setdefault(L, []).append(t)
        for L, words in by_line.items():
            if L not in kept and any(mask_token(t) != "#" for t in words):
                shapes.add(mask_line(words))
    return sorted(shapes)


def _settle_bands(rows, lines, rcols, bands):
    # an item may open with a short value printed alone above the rest (a line number): it starts right after the item before
    last = []
    for (a, b), r in zip(bands, rows):
        toks = [(L, t) for L in range(a, b) for t in lines[L][1]]
        where, tail, _ = _place(r, toks, rcols)
        ends = [toks[e - 1][0] for _, e in list(where.values()) + list(tail.values())]
        last.append(max(ends) if ends else None)
    out = list(bands)
    for i in range(1, len(out)):
        if last[i - 1] is not None and out[i - 1][0] <= last[i - 1] < out[i][0] - 1:
            out[i - 1], out[i] = (out[i - 1][0], last[i - 1] + 1), (last[i - 1] + 1, out[i][1])
    own = {str(rows[0].get(c)).strip() for c in rcols if rows[0].get(c)}

    def belongs(t):
        return t in own or any(len(v) >= config.LAYOUT_MIN_CUT_VALUE and len(t) > len(v) and (t.endswith(v) or t.startswith(v)) for v in own)
    a = out[0][0]
    while a > 0 and out[0][0] - a < config.LAYOUT_LEAD_ABOVE and all(belongs(t) for t in lines[a - 1][1]):
        a -= 1
    out[0] = (a, out[0][1])
    return out


def _merged_order(votes):
    # the commonest column order, with columns only some rows have (cartons in some, pieces in others) slotted in where they print
    seqs = sorted(votes, key=lambda q: (-votes[q], -len(q)))
    order = list(seqs[0])
    for q in seqs[1:]:
        for k, c in enumerate(q):
            if c not in order:
                before = next((q[j] for j in range(k - 1, -1, -1) if q[j] in order), None)
                order.insert(order.index(before) + 1 if before else 0, c)
    return order


def _counts_up(c, rows):
    # a line number, 1, 2, 3 ... in every document: any number of digits may follow
    by_doc = {}
    for r in rows:
        by_doc.setdefault(r.get("_doc", 0), []).append(str(r.get(c, "")))
    return len(rows) > 1 and all(v == [str(i) for i in range(1, len(v) + 1)] for v in by_doc.values())


def _alternatives(spec, rows):
    # optional columns side by side that never both hold a value in one row: only where they sit tells them apart
    groups, run = [], []
    for col in spec + [None]:
        if col and col["optional"] and not col["var"] and not col.get("skip"):
            run.append(col)
            continue
        if len(run) > 1 and all(sum(bool(r.get(c["col"])) for c in run) <= 1 for r in rows):
            groups.append(run)
        run = []
    return groups


def _homes(group, spots):
    # each column prints in a spot of its own across the page; values sitting in another column's spot are mistakes in the sheet
    every = sorted(x for xs in spots.values() for x in xs)
    widest = sorted(range(1, len(every)), key=lambda i: every[i] - every[i - 1], reverse=True)[:len(group) - 1]
    cuts = sorted(every[i] for i in widest if every[i] - every[i - 1] >= config.LAYOUT_SPOT_GAP)
    homes, owner = {}, {}
    for col in group:
        name = col["col"]
        votes = Counter(bisect_right(cuts, x) for x in spots[name])
        home, n = votes.most_common(1)[0]
        if home in owner:
            raise Unlearnable(f'{n} of {len(spots[name])} "{name}" values are printed under "{owner[home]}" on the PDF: check those rows')
        stray = len(spots[name]) - n
        if stray > (1 - config.LAYOUT_TRUST) * len(spots[name]):
            raise Unlearnable(f'{stray} of {len(spots[name])} "{name}" values are printed under another column on the PDF: check those rows')
        owner[home] = name
        homes[name] = round(median(x for x in spots[name] if bisect_right(cuts, x) == home), 4)
    return homes


def _anchors(spec, k):
    # the nearest columns either side that every row has: a column's place is measured between them
    steady = [j for j, col in enumerate(spec) if not col["var"] and not col["optional"]]
    before = next((spec[j]["col"] for j in reversed(steady) if j < k), None)
    after = next((spec[j]["col"] for j in steady if j > k), None)
    return before, after


def _between(spot_rows, name, before, after):
    # where each value sits between its neighbours on the same line, 0 at the one before and 1 at the one after
    out = []
    for row in spot_rows:
        if name in row and before in row and after in row:
            (lc, xc), (lb, xb), (la, xa) = row[name], row[before], row[after]
            if lc == lb == la and None not in (xc, xb, xa) and xa != xb:
                out.append((xc - xb) / (xa - xb))
    return out


def _learn_spots(spec, spot_rows, rows):
    groups = _alternatives(spec, rows)
    for group in groups:
        before, after = _anchors(spec, spec.index(group[0]))
        spots = {col["col"]: _between(spot_rows, col["col"], before, after) if before and after else [] for col in group}
        if not all(spots.values()):
            raise Unlearnable(f'"{group[0]["col"]}" and "{group[1]["col"]}" can only be told apart by where they sit on the page')
        homes = _homes(group, spots)
        for col in group:
            col["spot"], col["between"], col["alt"] = homes[col["col"]], [before, after], group[0]["col"]
    # a column keeping one place between its neighbours keeps it, so a value printed under another column is never taken for it
    for k, col in enumerate(spec):
        before, after = _anchors(spec, k)
        if "spot" in col or col["var"] or col.get("skip") or not before or not after or col["col"] in (before, after):
            continue
        spots = sorted(_between(spot_rows, col["col"], before, after))
        if len(spots) < 2:
            continue
        if spots[-1] - spots[0] <= config.LAYOUT_SPOT_SPREAD:
            col["spot"], col["between"] = round(median(spots), 4), [before, after]
            continue
        cut = max(range(1, len(spots)), key=lambda i: spots[i] - spots[i - 1])
        left, right = spots[:cut], spots[cut:]
        numbers = all(re.fullmatch(r"[\d.,]+", str(r.get(col["col"]))) for r in rows if r.get(col["col"]))
        if (numbers and len(left) > 1 and len(right) > 1 and spots[cut] - spots[cut - 1] >= config.LAYOUT_SPOT_GAP
                and left[-1] - left[0] <= config.LAYOUT_SPOT_SPREAD and right[-1] - right[0] <= config.LAYOUT_SPOT_SPREAD):
            raise Unlearnable(f'"{col["col"]}" values are printed under two different columns on the PDF: check the sheet')


def learn(table, texts):
    rcols = [c["name"] for c in table["columns"] if c.get("kind") != "doc"]
    names = {c["name"]: word_set(c["name"]) | {w for a in c.get("aliases") or [] for w in word_set(a)} for c in table["columns"]}
    table = join_pieces(table)
    segs = doc_pages(table, texts)

    placed, found, seg_lines, cut_of, spot_rows, skipped, one_page = [], Counter(), [], {}, [], {}, set()
    for rows, pages in segs:
        page_texts = [texts[p] for p in pages]
        lines, middles = split_lines(page_texts), line_middles(page_texts)
        line_len = {i: len(toks) for i, (_, toks) in enumerate(lines)}
        bands = _settle_bands(rows, lines, rcols, table_bands({"columns": table["columns"], "rows": rows}, lines))
        seg_lines.append((rows, lines, bands))
        for i, r in enumerate(rows):
            a, b = bands[i]
            toks = [(L, t) for L in range(a, b) for t in lines[L][1]]
            mids = [x for L in range(a, b) for x in middles[L]]
            where, tail, cut = _place(r, toks, rcols)
            found.update(where.keys())
            cut_of[id(r)] = cut
            spot_rows.append({c: (toks[s][0], mids[s]) for c, (s, _) in where.items()})
            placed.append((r, toks, where, tail, line_len))
            if lines[a][0] == lines[b - 1][0]:
                one_page.add(id(r))

    all_rows = [r for r, *_ in placed]
    in_row, by_label = [], []
    for c in rcols:
        filled = [r for r in all_rows if r.get(c)]
        if filled and found[c] >= config.LAYOUT_TRUST * len(filled):
            in_row.append(c)
        elif sum(len({r[c] for r in rows if r.get(c)}) <= 1 for rows, _ in segs) >= config.LAYOUT_FIELD_TRUST * len(segs):
            by_label.append(c)
        else:
            raise Unlearnable(f'"{c}" couldn\'t be located in its rows')
    # once it is known which columns sit in the rows, printed words between them that the sheet left out are parts to skip
    for _, toks, where, tail, _ in placed:
        gaps = _gaps({c: where[c] for c in where if c in in_row}, tail, toks)
        where.update(gaps)
        skipped.update(dict.fromkeys(gaps))
    in_row += list(skipped)

    # the structure comes from the rows that agree; a few rows the model got wrong are left out
    def seq_of(where):
        return tuple(c for c in sorted(where, key=lambda c: where[c][0]) if c in in_row)

    complete = [(r, toks, where, tail, ll) for r, toks, where, tail, ll in placed if all(c in where for c in in_row if r.get(c))]
    votes = Counter(seq_of(where) for _, _, where, _, _ in complete)
    if not votes:
        raise Unlearnable("rows don't share one column order")
    order = _merged_order(votes)
    sizes = {c: Counter(where[c][1] - where[c][0] for _, _, where, _, _ in complete if c in where) for c in in_row}
    fixed = {c for c, cnt in sizes.items() if cnt and max(cnt.values()) >= 0.8 * sum(cnt.values()) and max(cnt) <= 4}
    rare = {c: {n for n, k in sizes[c].items() if k < (1 - config.LAYOUT_TRUST) * sum(sizes[c].values())} for c in fixed}
    # spilled text belongs to a free-length text column, never to a column that almost always has one shape
    tail_votes = Counter(c for _, _, _, tail, _ in complete for c in tail)
    free = [c for c in tail_votes if c not in fixed]
    main_tail = max(free or tail_votes, key=lambda c: tail_votes[c]) if tail_votes else None

    def fits(toks, where, tail):
        if any(c != main_tail for c in tail):
            return False
        if any(where[c][1] - where[c][0] in rare.get(c, ()) for c in where if c in rare):
            return False
        it = iter(order)
        if not all(c in it for c in seq_of(where)):
            return False
        spans = sorted(where[c] for c in seq_of(where))
        if any(e1 != s2 for (_, e1), (s2, _) in zip(spans, spans[1:])):
            return False
        return not (spans and spans[0][0] > 0 and toks[spans[0][0] - 1][0] == toks[spans[0][0]][0])

    good = [x for x in complete if fits(x[1], x[2], x[3])]
    if len(placed) - len(good) > (1 - config.LAYOUT_TRUST) * len(placed):
        raise Unlearnable(f"{len(placed) - len(good)} of {len(placed)} rows in the sheet don't match the PDF")
    placed = good
    tails = {main_tail} if main_tail and any(main_tail in tail for _, _, _, tail, _ in placed) else set()
    spec = []
    for k, c in enumerate(order):
        counts = {where[c][1] - where[c][0] for _, _, where, _, _ in placed if c in where}
        if not counts and c in skipped:
            # a part to skip seen only in rows that were set aside isn't part of the layout
            continue
        col = {"col": c, "optional": any(not r.get(c) for r in all_rows)}
        if c in skipped:
            col.update(optional=any(c not in where for _, _, where, _, _ in placed), skip=True)
        col["var"] = max(counts) > 4 or len(counts) > 3 or c in tails
        if col["var"]:
            col["glue"] = c not in skipped and _learn_glue(c, placed)
            if c in tails:
                col["tail"] = tidy_classes({"INT" if x.startswith("INT:") else x
                                     for _, toks, _, tail, _ in placed if c in tail for _, t in toks[tail[c][0]:tail[c][1]] for x in [token_class(t)]})
        else:
            seqs = {}
            for _, toks, where, _, _ in placed:
                if c in where:
                    part = toks[where[c][0]:where[c][1]]
                    pos = seqs.setdefault(str(len(part)), [set() for _ in part])
                    for j, (_, t) in enumerate(part):
                        pos[j].add(token_class(t))
            col["seqs"] = {n: [tidy_classes(p, widen=k > 0) for p in pos] for n, pos in seqs.items()}
            if list(col["seqs"]) == ["1"] and _counts_up(c, all_rows):
                col["seqs"] = {"1": [[f"INT:1-{config.LAYOUT_LINE_NUMBER_DIGITS}"]]}
            cuts = Counter(cut_of[id(r)].get(c) for r, _, where, _, _ in placed if c in where)
            (kind_text, n), total = cuts.most_common(1)[0], sum(cuts.values())
            if kind_text and n < config.LAYOUT_TRUST * total:
                raise Unlearnable(f'"{c}" is cut out of the printed words in different ways')
            if kind_text:
                col["cut"] = {kind_text[0]: kind_text[1]}
        spec.append(col)
    _learn_spots(spec, spot_rows, all_rows)
    lead = []
    for col in spec:
        if col["var"] or col["optional"] or len(col["seqs"]) > 1:
            break
        lead.append(col)
    if not lead:
        first = spec[0]
        why = "it is optional" if first["optional"] else "its length varies" if first["var"] else "it comes in several shapes"
        raise Unlearnable(f'rows have no fixed opening column ("{first["col"]}" cannot open a row: {why})')
    lead_lines = 1
    for _, toks, where, _, _ in placed:
        cs = [where[c["col"]] for c in lead if c["col"] in where]
        if cs:
            lead_lines = max(lead_lines, toks[cs[-1][1] - 1][0] - toks[cs[0][0]][0] + 1)

    fields = {}
    for c in [x["name"] for x in table["columns"] if x.get("kind") == "doc"] + by_label:
        pairs = [(lines, next((r[c] for r in rows if r.get(c)), "")) for rows, lines, _ in seg_lines]
        pairs = [(ln, v) for ln, v in pairs if v]
        if not pairs:
            fields[c] = {"empty": True}
            continue
        rule = field_rule(names[c], pairs)
        if not rule:
            raise Unlearnable(f'"{c}" couldn\'t be found by its label')
        fields[c] = rule

    split_by = None
    if len(segs) > 1:
        ids = [c for c in fields if not fields[c].get("empty")
               and len({rows[0].get(c) for rows, _ in segs}) == len(segs)
               and all(set(v for t in (texts[p] for p in pages) for v in apply_rule(fields[c], split_lines([t]))[:1]) == {rows[0].get(c)}
                       for rows, pages in segs)]
        if not ids:
            raise Unlearnable("couldn't tell the documents in the file apart")
        split_by = max(ids, key=lambda c: sum(bool(apply_rule(fields[c], split_lines([t]))) for t in texts))

    _, lines0, bands0 = seg_lines[0]
    first_line = bands0[0][0] if bands0 else 0
    header = [" ".join(lines0[L][1]) for L in range(max(0, first_line - 2), first_line)]
    variant = {"row": spec, "lead": len(lead), "lead_lines": lead_lines, "fields": fields, "header": header,
               "row_cols": in_row, "split_by": split_by, "skip_lines": _skip_lines(placed, one_page)}
    got, why = read_variant(variant, texts)
    if got is None:
        raise Unlearnable(f"the confirmed sheet couldn't be read back ({why})")
    loose = {c["col"] for c in spec if c["var"]} | {c for c, r in fields.items() if "block" in r}
    same = lambda c, a, b: (c in fields and not b) or (similar(a, b) if c in loose else a == b)
    if len(got) != len(all_rows):
        raise Unlearnable(f"reading it back found {len(got)} rows instead of {len(all_rows)}")
    # header values count once per document, row values once per row
    diffs = [(i, c) for i, r in enumerate(all_rows) for c in rcols if c not in fields
             and not same(c, got[i].get(c, "") or "", r.get(c, "") or "")]
    heads = {}
    for i, r in enumerate(all_rows):
        heads.setdefault(r.get("_doc", 0), i)
    diffs += [(i, c) for i in heads.values() for c in fields if not same(c, got[i].get(c, "") or "", all_rows[i].get(c, "") or "")]
    cells = len(all_rows) * len([c for c in rcols if c not in fields]) + len(heads) * len(fields)
    variant["disagree"] = len(diffs)
    if len(diffs) > (1 - config.LAYOUT_MATCH) * cells:
        i, c = diffs[0]
        raise Unlearnable(f'reading it back gave {len(diffs)} different cell{"" if len(diffs) == 1 else "s"}, '
                          f'e.g. row {i + 1} "{c}": {got[i].get(c, "")!r} instead of {all_rows[i].get(c, "")!r}')
    return variant


def _learn_glue(c, placed):
    # a line holding one long word that runs on: rejoin it with no space unless the confirmed sheet says otherwise
    score = Counter()
    for r, toks, where, tail, line_len in placed:
        if c not in where:
            continue
        part = toks[where[c][0]:where[c][1]]
        joined = {glue: join_tokens(part, line_len, glue) for glue in (False, True)}
        if joined[False] != joined[True]:
            want = r[c] if c not in tail else r[c][:len(r[c]) - len(" ".join(t for _, t in toks[tail[c][0]:tail[c][1]]))].rstrip()
            for glue, text in joined.items():
                score[glue] += text == want
    return score[True] >= score[False]
