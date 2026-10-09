from core import activity, pdftext
from modules.companion import dialogue
from modules.conversion import reading
from modules.documents import repository as documents, transcript
from modules.profiles import matching, repository as profiles


LINE_FOR = {"confident": "converted", "best guess": "converted", "new": "converted_new",
            "scanned": "converted_scanned", "reused": "converted_reused"}


def possible_formats(conn, d):
    # the format whose words clearly match, or every format tied for it; none for a scan or a format never taught
    if not d["has_text_layer"]:
        return []
    m = matching.match(d["tokens"], d["structural"], profiles.list_all(conn))
    if m["decision"] == "propose":
        return [m["best"]["id"]]
    return [c["id"] for c in m.get("candidates") or []] if m["decision"] == "pick" else []


def convert(conn, d, pdf):
    # an emailed file is read only by what its format has learned, the same way every time; no model is ever asked here
    prev = documents.reusable(conn, d["sha256"], exclude=d["id"])
    if prev:
        for k in ("table", "verification", "profile_id", "signature"):
            d[k] = prev.get(k)
        d["auto_how"] = "reused"
        return _finish(conn, d, "same file as before, result reused")
    tried = [p for p in (profiles.get(conn, pid) for pid in possible_formats(conn, d)) if p]
    if not tried:
        return _not_read(d, "scanned, no text to read" if not d["has_text_layer"] else "unknown format")
    texts = pdftext.page_texts(pdf)
    fits, misses = [], []
    for prof in tried:
        table, ver, note = reading.read_direct(conn, d, prof, texts)
        (fits if table else misses).append((prof, table, ver, note))
    if not fits:
        prof, _, _, note = misses[0]
        d["profile_id"], d["read_note"] = prof["id"], note
        return _not_read(d, f"{prof['name']}, {note or 'layout not learned yet'}")
    # formats that both read the file perfectly can't be told apart by what is printed: the one taught last wins
    prof, table, ver, _ = max(fits, key=lambda f: f[0].get("updated_at") or "")
    if len(fits) > 1:
        activity.note(f"{d['filename']}: fits {', '.join(f[0]['name'] for f in fits)}; using {prof['name']}, the one taught last")
    d["table"], d["signature"], d["profile_id"], d["auto_how"], d["verification"] = table, prof.get("signature") or {}, prof["id"], "confident", ver
    d["read_note"] = None
    return _finish(conn, d, f"{prof['name']}, fast read")


def _not_read(d, why):
    activity.note(f"Not read: {d['filename']}: {why}; open it in Profile Builder")
    d["stage"], d["error"] = "failed", f"{why}; open it in Profile Builder"
    return d


def _finish(conn, d, way):
    activity.note(f"Done: {d['filename']}: {way}, {activity.count(len(d['table']['rows']), 'row')}, {activity.checked(d['verification'])}")
    prof = profiles.get(conn, d["profile_id"]) if d.get("profile_id") else None
    d["stage"], d["error"] = "converted", None
    transcript.add(d, "bot", dialogue.say(LINE_FOR[d["auto_how"]], profile=(prof or {}).get("name", "?"), how=d["auto_how"]))
    return d
