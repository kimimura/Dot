import copy
import re
from datetime import datetime


class OpError(Exception):
    pass


def _col(t, name):
    if name is None:
        raise OpError("no column given")
    n = str(name).strip().lower()
    for c in t["columns"]:
        if c["name"].lower() == n:
            return c
    for c in t["columns"]:
        if n in c["name"].lower():
            return c
    raise OpError(f'No column called "{name}"')


def _row(t, idx):
    try:
        i = int(idx)
    except (TypeError, ValueError):
        raise OpError("row must be a number")
    if i < 0 or i >= len(t["rows"]):
        raise OpError(f"row {i + 1} doesn't exist")
    return i


def _unique(t, name, skip=None):
    names = {c["name"].lower() for c in t["columns"] if c is not skip}
    base, n, out = name, 2, name
    while out.lower() in names:
        out = f"{base} ({n})"
        n += 1
    return out


def _mark(edited, t, col, rows=None):
    for r in (rows if rows is not None else range(len(t["rows"]))):
        edited.add(f"{r}|{col}")


# ── ops ──────────────────────────────────────────────────────────────────────

def rename_col(t, op, edited):
    c = _col(t, op.get("col"))
    new = str(op.get("new_name", "")).strip()[:60]
    if not new:
        raise OpError("new name is empty")
    old = c["name"]
    new = _unique(t, new, skip=c)
    c["name"] = new
    for r in t["rows"]:
        r[new] = r.pop(old, "")
    for k in list(edited):
        if k.endswith("|" + old):
            edited.add(k[: k.rfind("|")] + "|" + new)
    return f'Renamed "{old}" to "{new}"', {"renamed": {"old": old, "new": new}}


def drop_col(t, op, edited):
    c = _col(t, op.get("col"))
    t["columns"].remove(c)
    for r in t["rows"]:
        r.pop(c["name"], None)
    return f'Dropped "{c["name"]}"'


def _fill(t, name, op):
    # values come one per row, one per document (in order), or as a single value for every row
    vals = op.get("values")
    if not isinstance(vals, list):
        v = op.get("value", "")
        for r in t["rows"]:
            r[name] = "" if v is None else str(v)
        return False
    docs = list(dict.fromkeys(r.get("_doc", 0) for r in t["rows"]))
    if len(vals) == len(t["rows"]):
        for r, v in zip(t["rows"], vals):
            r[name] = "" if v is None else str(v)
        return False
    if len(vals) == len(docs):
        by_doc = dict(zip(docs, vals))
        for r in t["rows"]:
            v = by_doc[r.get("_doc", 0)]
            r[name] = "" if v is None else str(v)
        return True
    per = f" or {len(docs)} (one per document)" if len(docs) > 1 else ""
    raise OpError(f'"{name}" needs {len(t["rows"])} values (one per row){per}, got {len(vals)}')


def add_col(t, op, edited):
    name = _unique(t, str(op.get("name", "")).strip()[:60] or "New Column")
    probe = {"rows": [dict(r) for r in t["rows"]]}
    per_doc = _fill(probe, name, op)
    kind = "doc" if op.get("kind") == "doc" or per_doc else "row"
    t["columns"].append({"name": name, "kind": kind})
    for r, p in zip(t["rows"], probe["rows"]):
        r[name] = p[name]
    if kind == "doc":
        t["columns"].sort(key=lambda x: 0 if x["kind"] == "doc" else 1)
    _mark(edited, t, name)
    return f'Added column "{name}"'


def extract_col(t, op, edited):
    c = _col(t, op.get("col"))
    try:
        rx = re.compile(str(op.get("pattern") or ""))
    except re.error as e:
        raise OpError(f"the pattern doesn't work: {e}")
    into = str(op.get("into") or "").strip()[:60] or c["name"] + " (part)"
    same = next((x for x in t["columns"] if x["name"].lower() == into.lower() and x is not c), None)
    if same and not any(r.get(same["name"]) for r in t["rows"]):
        name = same["name"]
    else:
        name = _unique(t, into)
        t["columns"].append({"name": name, "kind": c["kind"]})
    hits = 0
    for r in t["rows"]:
        m = rx.search(r.get(c["name"], "") or "")
        v = (m.group(1) if m.groups() else m.group(0)).strip() if m else ""
        r[name] = v or ""
        hits += bool(v)
    if not hits:
        raise OpError(f'the pattern matched nothing in "{c["name"]}"')
    return f'Filled "{name}" from "{c["name"]}" ({hits} of {len(t["rows"])} rows)'


def set_col(t, op, edited):
    c = _col(t, op.get("col"))
    _fill(t, c["name"], op)
    _mark(edited, t, c["name"])
    return f'Updated every value in "{c["name"]}"'


def set_cell(t, op, edited):
    c = _col(t, op.get("col"))
    i = _row(t, op.get("row"))
    v = "" if op.get("value") is None else str(op["value"])
    if c["kind"] == "doc":
        d = t["rows"][i].get("_doc", 0)
        idx = [k for k, r in enumerate(t["rows"]) if r.get("_doc", 0) == d]
    else:
        idx = [i]
    for k in idx:
        t["rows"][k][c["name"]] = v
    _mark(edited, t, c["name"], idx)
    return f'Set "{c["name"]}" on row {i + 1}' + (f" (and {len(idx) - 1} more)" if len(idx) > 1 else "")


def set_col_kind(t, op, edited):
    c = _col(t, op.get("col"))
    kind = "doc" if op.get("kind") == "doc" else "row"
    c["kind"] = kind
    t["columns"].sort(key=lambda x: 0 if x["kind"] == "doc" else 1)
    return f'"{c["name"]}" is now {"document-level" if kind == "doc" else "row-level"}'


def reorder_cols(t, op, edited):
    order = op.get("order") or []
    picked = []
    for n in order:
        try:
            c = _col(t, n)
        except OpError:
            continue
        if c not in picked:
            picked.append(c)
    rest = [c for c in t["columns"] if c not in picked]
    t["columns"] = picked + rest
    return "Reordered columns"


def split_col(t, op, edited):
    c = _col(t, op.get("col"))
    into = [str(x).strip()[:60] for x in (op.get("into") or []) if str(x).strip()]
    if len(into) < 2:
        raise OpError("split needs at least two target names")
    pattern = op.get("pattern") or re.escape(str(op.get("sep") or " "))
    keep = bool(op.get("keep"))
    taken = {x["name"].lower() for x in t["columns"] if keep or x is not c}
    names = []
    for n in into:
        out, k = n, 2
        while out.lower() in taken:
            out, k = f"{n} ({k})", k + 1
        taken.add(out.lower())
        names.append(out)
    pos = t["columns"].index(c)
    new_cols = [{"name": n, "kind": c["kind"]} for n in names]
    for r in t["rows"]:
        parts = re.split(pattern, r.get(c["name"], ""), maxsplit=len(names) - 1)
        if not keep:
            r.pop(c["name"], None)
        for n, v in zip(names, parts + [""] * len(names)):
            r[n] = v.strip()
    if keep:
        t["columns"][pos + 1:pos + 1] = new_cols
    else:
        t["columns"][pos:pos + 1] = new_cols
    for n in names:
        _mark(edited, t, n)
    return f'Split "{c["name"]}" into {", ".join(names)}'


def merge_cols(t, op, edited):
    cols = [_col(t, n) for n in (op.get("cols") or [])]
    if len(cols) < 2:
        raise OpError("merge needs at least two columns")
    sep = str(op.get("sep", " "))
    into = str(op.get("into") or " ".join(c["name"] for c in cols))[:60]
    taken = {x["name"].lower() for x in t["columns"] if x not in cols}
    base, k = into, 2
    while into.lower() in taken:
        into, k = f"{base} ({k})", k + 1
    pos = t["columns"].index(cols[0])
    for r in t["rows"]:
        v = sep.join(x for x in (r.get(c["name"], "") for c in cols) if x)
        for c in cols:
            r.pop(c["name"], None)
        r[into] = v
    for c in cols:
        t["columns"].remove(c)
    t["columns"].insert(pos, {"name": into, "kind": cols[0]["kind"]})
    _mark(edited, t, into)
    return f'Merged into "{into}"'


DATE_PATTERNS = ["%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d %b %Y", "%d %B %Y",
                 "%b %d, %Y", "%B %d, %Y", "%d/%m/%y", "%d-%m-%y", "%d %b %y", "%Y%m%d", "%d-%b-%Y", "%d-%b-%y"]


def _to_date(v, fmt):
    s = v.strip()
    for p in DATE_PATTERNS:
        try:
            return datetime.strptime(s, p).strftime(fmt)
        except ValueError:
            continue
    return None


def _to_number(v):
    s = re.sub(r"[^\d.\-]", "", v.replace(",", ""))
    if not s or s in ("-", ".", "-."):
        return None
    try:
        f = float(s)
    except ValueError:
        return None
    return f


def transform_col(t, op, edited):
    c = _col(t, op.get("col"))
    kind = str(op.get("kind", "trim")).lower()
    fmt = op.get("format") or "%Y-%m-%d"
    missed = 0
    for r in t["rows"]:
        v = r.get(c["name"], "")
        if not v:
            continue
        if kind == "upper":
            r[c["name"]] = v.upper()
        elif kind == "lower":
            r[c["name"]] = v.lower()
        elif kind == "trim":
            r[c["name"]] = re.sub(r"\s+", " ", v).strip()
        elif kind == "date":
            d = _to_date(v, fmt)
            if d is None:
                missed += 1
            else:
                r[c["name"]] = d
        elif kind in ("number", "currency"):
            n = _to_number(v)
            if n is None:
                missed += 1
            else:
                r[c["name"]] = (f"{n:,.2f}" if kind == "currency" else (str(int(n)) if n == int(n) else f"{n:g}"))
        else:
            raise OpError(f"unknown transform {kind}")
    _mark(edited, t, c["name"])
    note = f" ({missed} values left as-is)" if missed else ""
    return f'Reformatted "{c["name"]}" as {kind}{note}'


def fill_down(t, op, edited):
    c = _col(t, op.get("col"))
    last, n = "", 0
    for i, r in enumerate(t["rows"]):
        if r.get(c["name"], ""):
            last = r[c["name"]]
        elif last:
            r[c["name"]] = last
            edited.add(f"{i}|{c['name']}")
            n += 1
    return f'Filled {n} blank cells in "{c["name"]}"'


def drop_row(t, op, edited):
    rows = op.get("rows")
    idx = sorted({_row(t, i) for i in (rows if isinstance(rows, list) else [op.get("row")])}, reverse=True)
    for i in idx:
        t["rows"].pop(i)
    if not t["rows"]:
        t["rows"].append({"_doc": 0, **{c["name"]: "" for c in t["columns"]}})
    edited.clear()
    return f"Removed {len(idx)} row" + ("s" if len(idx) != 1 else "")


def add_row(t, op, edited):
    vals = op.get("values") or {}
    r = {"_doc": t["rows"][-1].get("_doc", 0) if t["rows"] else 0}
    for c in t["columns"]:
        v = vals.get(c["name"], "")
        r[c["name"]] = "" if v is None else str(v)
    t["rows"].append(r)
    _mark(edited, t, None, [])
    for c in t["columns"]:
        edited.add(f"{len(t['rows']) - 1}|{c['name']}")
    return "Added a row"


OPS = {
    "rename_col": rename_col, "drop_col": drop_col, "add_col": add_col, "set_col": set_col,
    "set_cell": set_cell, "set_col_kind": set_col_kind, "reorder_cols": reorder_cols,
    "split_col": split_col, "merge_cols": merge_cols, "transform_col": transform_col, "extract_col": extract_col,
    "fill_down": fill_down, "drop_row": drop_row, "add_row": add_row,
}


def apply_ops(table, ops, edited=None):
    t = copy.deepcopy(table)
    edited = set(edited or ())
    changes = []
    for op in ops or []:
        name = (op or {}).get("op")
        fn = OPS.get(name)
        if not fn:
            changes.append({"ok": False, "text": f"I don't know how to do '{name}'"})
            continue
        before, marks = copy.deepcopy(t), set(edited)
        try:
            res = fn(t, op, edited)
            msg, extra = res if isinstance(res, tuple) else (res, {})
            changes.append({"ok": True, "text": msg, **extra})
        except OpError as e:
            t, edited = before, marks
            changes.append({"ok": False, "text": str(e)})
    return t, changes, edited
