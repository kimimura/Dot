import re

import config
from modules.reading import doc_groups

DATE = re.compile(r"^(\d{1,4})[/.-](\d{1,2})[/.-](\d{1,4})(?:\s+(\d{1,2}:\d{2}(?::\d{2})?))?$")


def key_of(column):
    # a column linked to a standard field takes its name; any other keeps its own, written the same way
    return column.get("field") or re.sub(r"[^a-z0-9]+", "_", column["name"].lower()).strip("_") or "column"


def standard_date(value, order):
    m = DATE.match(value.strip())
    if not m:
        return value
    parts = dict(zip(order, m.groups()[:3]))
    y, mo, d = parts["y"], parts["m"], parts["d"]
    if len(y) == 2:
        y = "20" + y
    if len(y) != 4 or not (1 <= int(mo) <= 12 and 1 <= int(d) <= 31):
        return value
    out = f"{y}-{int(mo):02d}-{int(d):02d}"
    if m.group(4):
        hms = m.group(4).split(":")
        out += " " + ":".join(f"{int(x):02d}" for x in hms + ["0"] * (3 - len(hms)))
    return out


def build(table, chain, date_order, process_date):
    order = date_order if date_order in config.OUTPUT_DATE_ORDERS else config.OUTPUT_DATE_ORDER_DEFAULT
    cols = [(c["name"], key_of(c), c.get("kind") == "doc") for c in table["columns"]]
    value = lambda row, name: standard_date(str(row.get(name) or "").strip(), order)
    orders, current = [], None
    # one entry per order in the file, in the order the orders appear
    for row, group in zip(table["rows"], doc_groups.groups(table)):
        if current is None or current[0] != group:
            fields = {key: value(row, name) for name, key, is_doc in cols if is_doc}
            current = (group, {**fields, "rows": []})
            orders.append(current[1])
        current[1]["rows"].append({key: value(row, name) for name, key, is_doc in cols if not is_doc})
    return {"chain": chain, "process_date": process_date, "orders": orders}
