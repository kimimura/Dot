from core import activity, pdftext
from modules.companion import dialogue
from modules.conversion import reading
from modules.documents import repository as documents, transcript
from modules.profiles import matching, repository as profiles


LINE_FOR = {"confident": "converted", "best guess": "converted", "new": "converted_new",
            "scanned": "converted_scanned", "reused": "converted_reused"}


def choose_format(conn, d):
    if not d["has_text_layer"]:
        return None, "scanned"
    m = matching.match(d["tokens"], d["structural"], profiles.list_all(conn))
    if m["decision"] == "propose":
        return m["best"]["id"], "confident" if m["strong"] else "best guess"
    if m["decision"] == "pick" and m.get("candidates"):
        return m["candidates"][0]["id"], "best guess"
    return None, "new"


def convert(conn, llm, d, pdf):
    prev = documents.reusable(conn, d["sha256"], exclude=d["id"])
    if prev:
        for k in ("table", "verification", "profile_id", "signature"):
            d[k] = prev.get(k)
        d["auto_how"], way = "reused", "same file as before, result reused"
    else:
        pid, how = choose_format(conn, d)
        prof = profiles.get(conn, pid) if pid else None
        texts = pdftext.page_texts(pdf)
        table, ver, note = reading.read_direct(conn, d, prof, texts) if prof and d["has_text_layer"] else (None, None, None)
        if table:
            sig, how, way = prof.get("signature") or {}, "confident", f"{prof['name']}, fast read"
        else:
            table, ver, sig = reading.read_with_model(llm, d, pdf, prof, texts)
            way = f"{prof['name']}, read by the model" + (f" ({note})" if note else "") if prof else "unknown format, read by the model"
        d["table"], d["signature"], d["profile_id"], d["auto_how"] = table, sig, prof["id"] if prof else None, how
        d["verification"], d["read_note"] = ver, note
    activity.note(f"Done: {d['filename']}: {way}, {activity.count(len(d['table']['rows']), 'row')}, {activity.checked(d['verification'])}")
    prof = profiles.get(conn, d["profile_id"]) if d.get("profile_id") else None
    d["stage"], d["error"] = "converted", None
    transcript.add(d, "bot", dialogue.say(LINE_FOR[d["auto_how"]], profile=(prof or {}).get("name", "?"), how=d["auto_how"]))
    return d
