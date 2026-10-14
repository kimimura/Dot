import copy

from modules.reading import verify
from modules.reading.table_ops import OpError, _col


def whole(table, col, text, edited):
    # a value kept as part of a printed word (187054 out of FC-187054) gets the whole word back, found in its own row's lines
    ctx = verify.read_rows(table, text)
    if not ctx:
        raise OpError("the PDF has no text to take the printed words from")
    t, edited = copy.deepcopy(table), set(edited)
    name = _col(t, col)["name"]
    done = 0
    for i, r in enumerate(t["rows"]):
        v, at = (r.get(name) or "").strip(), ctx["own"][i] or ctx["spans"][i]
        if not v or " " in v or not at:
            continue
        words = [w for line in ctx["printed"][at[0]:at[1]] for w in line.split()]
        word = next((w for w in words if len(w) > len(v) and (w.endswith(v) or w.startswith(v))), None)
        if word:
            r[name] = word
            edited.discard(f"{i}|{name}")
            done += 1
    if not done:
        raise OpError(f'every "{name}" value is already printed whole')
    return t, [{"ok": True, "text": f'Took "{name}" as printed in full ({done} of {len(t["rows"])} rows)'}], edited
