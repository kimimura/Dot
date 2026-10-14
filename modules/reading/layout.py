import config
from modules.reading.layout_learn import lead_of, learn
from modules.reading.layout_places import Unlearnable
from modules.reading.layout_read import read_variant, seqs_of
from modules.reading.layout_tokens import cut_texts


def _key(col_name, known, prof_col):
    if col_name in known:
        return col_name
    return next((a for a in prof_col.get("aliases") or [] if a in known), None)


def read_table(layout, prof, texts):
    note = None
    for variant in (layout or {}).get("variants", []):
        known = set(variant["row_cols"]) | set(variant["fields"])
        keys = {c["name"]: _key(c["name"], known, c) for c in prof["columns"]}
        missing = [n for n, k in keys.items() if k is None]
        if missing:
            note = note or f'layout not learned for "{missing[0]}" yet'
            continue
        rows, why = read_variant(variant, texts)
        if rows is None:
            note = note or why
            continue
        cols = [{"name": c["name"], "kind": c.get("kind", "row")} for c in prof["columns"]]
        return {"columns": cols, "rows": [{"_doc": r.get("_doc", 0), **{n: r.get(k, "") for n, k in keys.items()}} for r in rows]}, None
    return None, note


def rename(layout, old, new):
    # a column renamed on the Profiles page keeps everything learned about it under its new name
    swap = lambda c: new if c == old else c
    for v in (layout or {}).get("variants", []):
        for col in v["row"]:
            col["col"] = swap(col["col"])
            if "between" in col:
                col["between"] = [swap(x) for x in col["between"]]
            if "alt" in col:
                col["alt"] = swap(col["alt"])
        v["row_cols"] = [swap(c) for c in v["row_cols"]]
        v["fields"] = {swap(c): r for c, r in v["fields"].items()}
        v["split_by"] = swap(v.get("split_by"))
    return layout


def _order(a, b):
    # one column order holding both; None when the two print their shared columns in a different order
    shared = [c for c in a if c in b]
    if shared != [c for c in b if c in a]:
        return None
    out = list(a)
    for k, c in enumerate(b):
        if c not in out:
            before = next((b[j] for j in range(k - 1, -1, -1) if b[j] in out), None)
            out.insert(out.index(before) + 1 if before else 0, c)
    return out


def _merge_col(a, b):
    col = {**a, **{k: v for k, v in b.items() if k not in ("spot", "between", "alt")}}
    col["optional"] = a["optional"] or b["optional"]
    col["skip"] = a.get("skip", False) or b.get("skip", False)
    if not col["skip"]:
        col.pop("skip")
    col["var"] = a["var"] or b["var"]
    col.pop("classes", None)
    if col["var"]:
        col.pop("seqs", None)
    else:
        sa, sb = seqs_of(a), seqs_of(b)
        col["seqs"] = {n: [sorted(set(p) | set(q)) for p, q in zip(sa[n], sb[n])] if n in sa and n in sb else (sa.get(n) or sb[n])
                       for n in sorted(set(sa) | set(sb), key=int)}
    # the newest confirmed sheet decides what a column keeps of a printed word: the cuts it still makes add to the ones learned, none means whole words
    col.pop("cut", None)
    if b.get("cut"):
        cut = {k: sorted(set(cut_texts(a.get("cut"), k)) | set(cut_texts(b.get("cut"), k))) for k in ("prefix", "suffix")}
        col["cut"] = {k: t[0] if len(t) == 1 else t for k, t in cut.items() if t}
    # where a column sits on the page is kept as first learned; a new file only adds a place when there was none
    for k in ("spot", "between", "alt"):
        col.pop(k, None)
        if k in a or k in b:
            col[k] = a[k] if k in a else b[k]
    return col


def _merge(old, new):
    # what a new confirmed file shows is added to the layout it shares columns with: columns only one of them prints become optional
    order = _order([c["col"] for c in old["row"]], [c["col"] for c in new["row"]])
    if order is None:
        return None
    a, b = {c["col"]: c for c in old["row"]}, {c["col"]: c for c in new["row"]}
    row = [_merge_col(a[c], b[c]) if c in a and c in b else {**(a.get(c) or b[c]), "optional": True} for c in order]
    lead = lead_of(row)
    if not lead:
        return None
    # a column read from the rows in either file stays a row column (one file's items may just all leave it empty)
    row_cols = _order(old["row_cols"], new["row_cols"]) or new["row_cols"]
    fields = {c: r for c, r in {**old["fields"], **new["fields"]}.items() if c not in row_cols}
    return {**old, **new, "row": row, "lead": len(lead), "lead_lines": max(old.get("lead_lines", 1), new.get("lead_lines", 1)),
            "fields": fields, "row_cols": row_cols, "split_by": new.get("split_by") or old.get("split_by"),
            "skip_lines": sorted(set(old.get("skip_lines") or ()) | set(new.get("skip_lines") or ()))}


def _reads_alike(a, b, texts):
    got_a, _ = read_variant(a, texts)
    got_b, _ = read_variant(b, texts)
    keys = set(b["row_cols"]) | set(b["fields"])
    return got_a is not None and got_b is not None and len(got_a) == len(got_b) and all(
        all(x.get(k, "") == y.get(k, "") for k in keys) for x, y in zip(got_a, got_b))


def add(layout, table, texts, doc_id):
    layout = layout or {"variants": [], "learned_from": []}
    try:
        v = learn(table, texts)
    except Unlearnable as e:
        layout["last_problem"] = str(e)
        return layout
    layout.pop("last_problem", None)
    for old in layout["variants"]:
        merged = _merge(old, v)
        if merged and _reads_alike(merged, v, texts):
            layout["variants"].remove(old)
            v = merged
            break
    layout["variants"] = ([v] + layout["variants"])[:config.LAYOUT_MAX_VARIANTS]
    layout["learned_from"] = ([doc_id] + [x for x in layout["learned_from"] if x != doc_id])[:config.LAYOUT_LEARN_FROM * 3]
    return layout
