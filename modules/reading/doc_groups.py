def key_column(table):
    doc_cols = [c["name"] for c in table["columns"] if c.get("kind") == "doc"]
    firsts = {}
    for r in table["rows"]:
        firsts.setdefault(r.get("_doc", 0), r)
    if len(firsts) < 2:
        return None
    usable = [c for c in doc_cols if all(r.get(c) for r in firsts.values())]
    # the field that tells documents apart best is the one with the most different values
    return max(usable, key=lambda c: (len({r[c] for r in firsts.values()}), -doc_cols.index(c)), default=None)


def groups(table):
    key = key_column(table)
    out, last_doc, last_key, n = [], None, None, -1
    for r in table["rows"]:
        doc = r.get("_doc", 0)
        if doc != last_doc:
            value = r.get(key) if key else None
            if not (key and value == last_key):
                n += 1
            last_doc, last_key = doc, value
        out.append(n)
    return out


def join_pages(table):
    # pages of one document read as separate documents share its id; they become one document again
    doc_cols = [c["name"] for c in table["columns"] if c.get("kind") == "doc"]
    ids = groups(table)
    rows = [{**r, "_doc": g} for r, g in zip(table["rows"], ids)]
    for g in set(ids):
        members = [r for r in rows if r["_doc"] == g]
        for c in doc_cols:
            values = {r.get(c) for r in members if r.get(c)}
            if len(values) == 1:
                value = values.pop()
                for r in members:
                    r[c] = r.get(c) or value
    return {**table, "rows": rows}
