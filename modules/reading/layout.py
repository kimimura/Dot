import config
from modules.reading.layout_learn import learn
from modules.reading.layout_places import Unlearnable
from modules.reading.layout_read import read_variant, seqs_of


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


def _shape(v):
    return ([(c["col"], c["var"], c["optional"], sorted(seqs_of(c)) if not c["var"] else None) for c in v["row"]],
            sorted(v["fields"]), v["lead"], v.get("lead_lines", 1), v.get("split_by"))


def add(layout, table, texts, doc_id):
    layout = layout or {"variants": [], "learned_from": []}
    try:
        v = learn(table, texts)
    except Unlearnable as e:
        layout["last_problem"] = str(e)
        return layout
    layout.pop("last_problem", None)
    same = next((x for x in layout["variants"] if _shape(x) == _shape(v)), None)
    if same:
        for a, b in zip(same["row"], v["row"]):
            if not a["var"]:
                sa = seqs_of(a)
                a["seqs"] = {n: [sorted(set(p) | set(q)) for p, q in zip(sa[n], seq)] for n, seq in seqs_of(b).items()}
                a.pop("classes", None)
            for key in ("glue", "tail"):
                if key in b:
                    a[key] = b[key]
        same["fields"], same["header"] = v["fields"], v["header"]
        same["skip_lines"] = sorted(set(same.get("skip_lines") or ()) | set(v.get("skip_lines") or ()))
        layout["variants"].remove(same)
        v = same
    layout["variants"] = ([v] + layout["variants"])[:config.LAYOUT_MAX_VARIANTS]
    layout["learned_from"] = ([doc_id] + [x for x in layout["learned_from"] if x != doc_id])[:config.LAYOUT_LEARN_FROM * 3]
    return layout
