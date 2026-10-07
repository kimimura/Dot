import csv
import io

import config


def with_sender(table, sender):
    # who sent the file is not printed on it, so it is added as a last column of its own on every row
    name = config.OUTPUT_SENDER_COLUMN
    return {"columns": table["columns"] + [{"name": name, "kind": "doc"}], "rows": [{**r, name: sender or ""} for r in table["rows"]]}


def csv_bytes(table):
    out = io.StringIO()
    cols = [c["name"] for c in table["columns"]]
    w = csv.writer(out)
    w.writerow(cols)
    for r in table["rows"]:
        w.writerow([r.get(c, "") for c in cols])
    return io.BytesIO(out.getvalue().encode("utf-8-sig"))
