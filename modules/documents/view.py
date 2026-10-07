import config
from core import jobs
from modules.companion import dialogue
from modules.documents import repository as documents
from modules.outputs import service as outputs
from modules.profiles import repository as profiles
from modules.submissions import repository as submissions


def options_for(conn, d):
    st = d["stage"]
    if st == "identify":
        opts = [{"id": "yes", "label": "Yes, that's it", "primary": True}, {"id": "no", "label": "No"}]
        if len(profiles.list_all(conn)) > 1:
            opts.append({"id": "pick", "label": "It's another format"})
        return opts, "none"
    if st in ("pick", "pick_existing"):
        cands = d.get("candidates") or []
        ids = {c["id"] for c in cands}
        allp = [p for p in profiles.list_all(conn) if p["id"] not in d.get("rejected_profile_ids", [])]
        listed = [{"id": f"profile:{c['id']}", "label": c["name"]} for c in cands]
        listed += [{"id": f"profile:{p['id']}", "label": p["name"]} for p in allp if p["id"] not in ids]
        if st == "pick":
            listed.append({"id": "new", "label": "It's a new format", "primary": True})
        else:
            listed.append({"id": "back", "label": "Back"})
        return listed, "none"
    if st == "duplicate":
        return [{"id": "yes", "label": "Read it again", "primary": True}, {"id": "open", "label": "Open the previous one"}], "none"
    if st == "review":
        return [{"id": "yes", "label": "Yes, that's the format", "primary": True}, {"id": "no", "label": "No, change some fields"}], "text"
    if st == "confirm_ops":
        return [{"id": "yes", "label": "Yes, do it"}, {"id": "no", "label": "No, leave it", "primary": True}], "none"
    if st == "revising":
        return [{"id": "looks_good", "label": "Actually, it looks right"}], "text"
    if st == "save_ask":
        opts = [{"id": "yes", "label": "Yes, save it", "primary": True}, {"id": "no", "label": "No, just the Library"}]
        if profiles.list_all(conn):
            opts.append({"id": "existing", "label": "Use an existing profile"})
        return opts, "none"
    if st == "naming":
        if d.get("pending_name"):
            return [{"id": "use_existing", "label": f"Use \"{d['pending_name']}\""}, {"id": "back", "label": "Back"}], "name"
        return [{"id": "back", "label": "Back"}], "name"
    if st == "confirmed":
        return [{"id": "new_upload", "label": "Upload another", "primary": True}, {"id": "revise", "label": "Revise this one"}], "none"
    if st == "failed":
        return [{"id": "retry", "label": "Try again", "primary": True}], "none"
    return [], "none"


STATE_FOR = {"identify": "asking", "pick": "asking", "pick_existing": "asking", "duplicate": "asking", "review": "asking", "confirm_ops": "asking",
             "revising": "asking", "save_ask": "asking", "naming": "asking", "confirmed": "happy", "failed": "confused",
             "extracting": "reading"}


def envelope(conn, d, changes=None):
    last_bot = next((t for t in reversed(d["transcript"]) if t["who"] == "bot"), None)
    options, inp = options_for(conn, d)
    prof = profiles.get(conn, d["profile_id"]) if d.get("profile_id") else None
    sub = submissions.get(conn, d["submission_id"]) if d.get("submission_id") else None
    has_output, base = outputs.ready(d), f"/api/docs/{d['id']}"
    return {
        "doc": {
            "id": d["id"], "filename": d["filename"], "stage": d["stage"], "error": d.get("error"),
            "n_pages": d["n_pages"], "uploaded_at": d["uploaded_at"], "confirmed_at": d.get("confirmed_at"),
            "has_text_layer": d["has_text_layer"], "profile_id": d.get("profile_id"),
            "profile_name": prof["name"] if prof else None, "duplicate_of": d.get("duplicate_of"),
            "teaches": bool(prof) and d["stage"] == "confirmed", "teachers": documents.teachers(conn, prof["id"]) if prof else 0,
            "source": sub["source"] if sub else None, "sender": sub["sender"] if sub else None,
            "sender_column": config.OUTPUT_SENDER_COLUMN,
            "has_output": has_output,
            "csv_url": f"{base}/download.csv" if d.get("table") else None,
            "json_url": f"{base}/download.json" if has_output else None,
            "pdf_url": f"{base}/download.pdf",
            "can_undo": bool(d.get("history")), "hints": d.get("hints", []), "extra_fields": d.get("extra_fields") or {},
            "signature": d.get("signature") or {},
            "reread_from": d.get("reread_from"), "reread_at": d.get("reread_at"), "reread_error": d.get("reread_error"),
            "can_undo_reread": bool(d.get("before_reread")), "read_note": d.get("read_note"),
        },
        "table": table_view(d),
        "bot": {"say": last_bot["text"] if last_bot else dialogue.say("welcome"), "state": STATE_FOR.get(d["stage"], "idle"),
                "options": options, "input": inp, "next": "extract" if d["stage"] == "extracting" else None},
        "transcript": d["transcript"],
        "changes": changes or [],
        "working": jobs.running(d["id"]),
        "progress": jobs.progress.get(d["id"]),
    }


def table_view(d):
    if not d.get("table"):
        return None
    t = d["table"]
    return {"columns": t["columns"], "rows": t["rows"], "verification": d.get("verification") or {"cells": {}, "verified": 0, "total": 0, "checked": False}}
