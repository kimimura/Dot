from modules.builder.edits import alias_hints, revise
from modules.builder.identify import identify
from modules.builder.review import ask_review
from modules.builder.saving import after_yes, confirm
from modules.documents import history, repository as documents, transcript
from modules.profiles import matching, repository as profiles


def on_answer(conn, llm, d, option, payload=None):
    payload = payload or {}
    st = d["stage"]
    label = payload.get("label") or option
    transcript.user(d, label, option=option)

    if st == "identify":
        pend = d.get("pending_profile_id")
        if option == "yes" and pend:
            _choose_profile(conn, d, pend)
        elif option.startswith("profile:"):
            _choose_profile(conn, d, option.split(":", 1)[1])
        elif option == "pick":
            d["stage"] = "pick"
            transcript.bot(d, "pick_after_no")
        else:
            if pend:
                d.setdefault("rejected_profile_ids", []).append(pend)
            usable = [p for p in profiles.list_all(conn) if p["id"] not in d["rejected_profile_ids"]]
            d["pending_profile_id"] = None
            if usable:
                m = matching.match(d["tokens"], d["structural"], usable) if d["has_text_layer"] else {}
                d["candidates"] = m.get("candidates", [])
                d["stage"] = "pick"
                transcript.bot(d, "pick_after_no")
            else:
                d["profile_id"], d["stage"] = None, "extracting"
                transcript.bot(d, "extracting_fresh")
    elif st == "pick":
        if option.startswith("profile:"):
            _choose_profile(conn, d, option.split(":", 1)[1])
        else:
            d["profile_id"] = None
            d["stage"] = "extracting"
            transcript.bot(d, "extracting_fresh")
    elif st == "duplicate":
        if option == "yes":
            identify(conn, d)
    elif st == "review":
        if option == "yes":
            after_yes(conn, d)
        else:
            d["stage"] = "revising"
            transcript.bot(d, "ask_changes")
    elif st == "confirm_ops":
        pend = d.get("pending") or {}
        d["pending"] = None
        if option == "yes" and pend.get("table"):
            history.snapshot(d)
            d["table"] = pend["table"]
            d["verification"] = pend["verification"]
            d["hints"] = pend.get("hints") or d["hints"]
            d["extra_fields"] = pend.get("extra_fields") or {}
            alias_hints(d, pend.get("changes") or [])
            ask_review(d, reply=pend.get("reply") or "Done.", applied=True)
        else:
            d["stage"] = "revising"
            transcript.bot(d, "cancelled")
    elif st == "revising":
        if option == "looks_good":
            after_yes(conn, d)
    elif st == "save_ask":
        if option == "yes":
            d["stage"], d["pending_name"] = "naming", None
            transcript.bot(d, "naming")
        elif option == "existing":
            d["stage"], d["candidates"] = "pick_existing", []
            transcript.bot(d, "pick")
        else:
            confirm(conn, d)
    elif st == "pick_existing":
        if option.startswith("profile:"):
            confirm(conn, d, profile_id=option.split(":", 1)[1])
        else:
            d["stage"] = "save_ask"
            transcript.bot(d, "save_ask")
    elif st == "naming":
        if option == "submit":
            name = (payload.get("name") or "").strip()[:60]
            if name:
                confirm(conn, d, new_name=name)
            else:
                transcript.bot(d, "naming")
        elif option == "use_existing" and d.get("pending_name"):
            p = profiles.by_name(conn, d["pending_name"])
            if p:
                confirm(conn, d, profile_id=p["id"])
        else:
            d["stage"], d["pending_name"] = "save_ask", None
            transcript.bot(d, "save_ask")
    elif st == "failed":
        if option == "retry":
            d["stage"], d["error"] = "extracting", None
            transcript.bot(d, "extracting_with" if d.get("profile_id") else "extracting_fresh",
                 profile=(profiles.get(conn, d["profile_id"]) or {}).get("name", "") if d.get("profile_id") else "")
    elif st == "confirmed":
        if option == "revise":
            revise(conn, d)
    documents.save(conn, d)
    return d


def _choose_profile(conn, d, pid):
    p = profiles.get(conn, pid)
    d["profile_id"] = pid if p else None
    d["stage"] = "extracting"
    if p:
        transcript.bot(d, "extracting_with", profile=p["name"])
    else:
        transcript.bot(d, "extracting_fresh")
