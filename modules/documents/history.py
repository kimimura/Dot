import config


def snapshot(d):
    d["history"].append({"table": d["table"], "verification": d["verification"], "hints": list(d["hints"])})
    d["history"] = d["history"][-config.UNDO_DEPTH:]


def undo(d):
    if not d["history"]:
        return False
    s = d["history"].pop()
    d["table"], d["verification"], d["hints"] = s["table"], s["verification"], s["hints"]
    return True
