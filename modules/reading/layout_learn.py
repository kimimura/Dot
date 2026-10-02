from collections import Counter

import config
from modules.reading.layout_places import (Unlearnable, doc_pages, field_rule, join_pieces, leftover_place,
                                           split_span, table_bands, value_spans)
from modules.reading.layout_read import read_variant
from modules.reading.layout_tokens import (apply_rule, join_tokens, similar, split_lines, tidy_classes,
                                           token_class, word_set)
from modules.reading.verify import norm_text


def learn(table, texts):
    rcols = [c["name"] for c in table["columns"] if c.get("kind") != "doc"]
    names = {c["name"]: word_set(c["name"]) | {w for a in c.get("aliases") or [] for w in word_set(a)} for c in table["columns"]}
    table = join_pieces(table)
    segs = doc_pages(table, texts)

    placed, found, seg_lines = [], Counter(), []
    for rows, pages in segs:
        lines = split_lines([texts[p] for p in pages])
        line_len = {i: len(toks) for i, (_, toks) in enumerate(lines)}
        bands = table_bands({"columns": table["columns"], "rows": rows}, lines)
        seg_lines.append((rows, lines, bands))
        for i, r in enumerate(rows):
            a, b = bands[i]
            toks = [(L, t) for L in range(a, b) for t in lines[L][1]]
            taken, where, tail = set(), {}, {}
            for c in sorted((c for c in rcols if r.get(c)), key=lambda c: (-len(norm_text(r[c])), rcols.index(c))):
                for s, e in value_spans(r[c], toks):
                    if not taken.intersection(range(s, e)):
                        where[c] = (s, e)
                        taken.update(range(s, e))
                        found[c] += 1
                        break
            missing = [c for c in rcols if r.get(c) and c not in where]
            if len(missing) == 1 and where:
                hit = leftover_place(r[missing[0]], toks, where)
                if hit:
                    where[missing[0]], end = hit
                    if end:
                        tail[missing[0]] = end
                    found[missing[0]] += 1
                    missing = []
            if missing and where:
                row_end = max(e for _, e in where.values())
                for c in missing:
                    hit = split_span(r[c], toks, taken, row_end)
                    if hit:
                        where[c], tail[c] = hit
                        taken.update(range(*hit[0]))
                        found[c] += 1
                        break
            placed.append((r, toks, where, tail, line_len))

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

    # the structure comes from the rows that agree; a few rows the model got wrong are left out
    def seq_of(where):
        return tuple(c for c in sorted(where, key=lambda c: where[c][0]) if c in in_row)

    complete = [(r, toks, where, tail, ll) for r, toks, where, tail, ll in placed if all(c in where for c in in_row if r.get(c))]
    votes = Counter(seq_of(where) for _, _, where, _, _ in complete)
    if not votes:
        raise Unlearnable("rows don't share one column order")
    order = list(max(votes, key=lambda q: (votes[q], len(q))))
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
        col = {"col": c, "optional": any(not r.get(c) for r in all_rows)}
        col["var"] = max(counts) > 4 or len(counts) > 3 or c in tails
        if col["var"]:
            col["glue"] = _learn_glue(c, placed)
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
        spec.append(col)
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
               "row_cols": in_row, "split_by": split_by}
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
