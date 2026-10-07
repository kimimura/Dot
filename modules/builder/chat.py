import difflib
import re

import config
from core import pdftext
from core.ai.errors import LLMError, Truncated
from modules.builder import chat_prompt
from modules.builder.answers import on_answer
from modules.builder.edits import alias_hints, column_notes, settle_hints
from modules.builder.review import ask_review
from modules.builder.saving import after_yes
from modules.companion import dialogue
from modules.documents import history, repository as documents, transcript
from modules.profiles import hints as hint_rules, repository as profiles
from modules.reading import column_reread, extract, table_ops, verify


YES = re.compile(r"^\s*(y|yes|yeah|yep|yup|correct|right|ok|okay|sure|looks good|that's it|thats it|perfect|good)\b", re.I)
NO = re.compile(r"^\s*(n|no|nope|wrong|nah|not (quite|really|this)|incorrect)\b", re.I)
INTENTS = {"edit", "question", "offtopic", "confirm", "reject"}


def _shrink(before, after):
    oc, nc = len(before["columns"]), len(after["columns"])
    orr, nr = len(before["rows"]), len(after["rows"])
    lost_c, lost_r = oc - nc, orr - nr
    if lost_c > 0 and (nc == 0 or (lost_c >= 3 and lost_c * 2 >= oc)):
        return "remove %d of your %d columns" % (lost_c, oc)
    if lost_r > 0 and (nr == 0 or (lost_r >= 5 and lost_r * 2 >= orr)):
        return "remove %d of your %d rows" % (lost_r, orr)
    return None


def _apply_revision(conn, llm, d, pdf, reply, op_list, new_hints, message="", forced=False):
    undo = next((o for o in op_list if o.get("op") == "undo"), None)
    if undo:
        try:
            steps = max(1, min(config.CHAT_MAX_UNDO_STEPS, int(undo.get("steps") or 1)))
        except (TypeError, ValueError):
            steps = 1
        done = 0
        while done < steps and history.undo(d):
            done += 1
        text = "Nothing to undo" if not done else "Undid the last change" if done == 1 else f"Undid the last {done} changes"
        ask_review(d, reply=reply, applied=bool(done))
        return [{"ok": bool(done), "text": text}]
    before = d["table"]
    table, extra = before, d.get("extra_fields")
    hints = list(d["hints"])
    changes = []
    re_ops = [o for o in op_list if o.get("op") == "reextract"]
    col_ops = [o for o in op_list if o.get("op") == "reread_cols"]
    other = [o for o in op_list if o.get("op") not in ("reextract", "reread_cols")]
    for h in new_hints:
        hints.append({"scope": h.get("scope", "profile"), "col": h.get("col"), "text": str(h["text"]).strip()})
    edited = {k for k, v in (d.get("verification") or {}).get("cells", {}).items() if v == "edited"}
    if re_ops:
        prof = profiles.get(conn, d["profile_id"]) if d.get("profile_id") else None
        try:
            table, sig, extra = extract.run(llm, pdf, prof, hints, instruction=re_ops[0].get("instruction") or message)
            edited = set()
            changes.append({"ok": True, "text": "Re-read the document"})
        except LLMError as e:
            changes.append({"ok": False, "text": "re-read failed: %s" % e})
    for o in col_ops:
        table, ch, edited = column_reread.run(llm, pdf, table, o.get("cols") or [o.get("col")], edited, column_notes(hints))
        changes += ch
    if other:
        for o in other:
            if o.get("op") == "drop_col":
                hints.append({"scope": "col", "col": str(o.get("col")), "text": 'Do not extract "%s"' % o.get("col"), "dropped": True})
        table, ch, edited = table_ops.apply_ops(table, other, edited, typed_by_model=True)
        changes += ch
        hints = settle_hints(hints, other, ch, table)
    verification = verify.verify(table, pdftext.text_of(pdf), d["has_text_layer"], edited=edited)

    danger = None if forced else _shrink(before, table)
    if danger:
        d["pending"] = {"table": table, "verification": verification, "hints": hints,
                        "extra_fields": extra, "changes": changes, "reply": reply}
        d["stage"] = "confirm_ops"
        transcript.bot(d, "confirm_destructive", what=danger)
        return []

    history.snapshot(d)
    d["table"], d["verification"], d["hints"], d["extra_fields"] = table, verification, hints, extra
    alias_hints(d, changes)
    applied = any(c["ok"] for c in changes)
    if changes and not applied:
        # nothing was made, so the reply says why rather than describing a change that didn't happen
        reply = changes[0]["text"]
    ask_review(d, reply=reply, applied=applied)
    return changes


def on_chat(conn, llm, d, pdf, message):
    st = d["stage"]
    msg = message.strip()
    transcript.user(d, msg)
    changes = []

    if st == "confirm_ops":
        d["transcript"].pop()
        return on_answer(conn, llm, d, "yes" if YES.match(msg) else "no", {"label": msg})
    if st in ("identify", "pick", "pick_existing", "duplicate", "save_ask", "failed"):
        opt = _text_to_option(conn, d, msg)
        if opt:
            d["transcript"].pop()
            return on_answer(conn, llm, d, opt, {"label": msg})
        transcript.bot(d, text=next(t["text"] for t in reversed(d["transcript"][:-1]) if t["who"] == "bot"))
    elif st == "naming":
        d["transcript"].pop()
        return on_answer(conn, llm, d, "submit", {"label": msg, "name": msg})
    elif st == "review" and YES.match(msg):
        after_yes(conn, d)
    elif st == "review" and NO.match(msg) and len(msg.split()) <= 3:
        d["stage"] = "revising"
        transcript.bot(d, "ask_changes")
    elif st in ("review", "revising", "confirmed"):
        if st == "revising" and YES.match(msg) and len(msg.split()) <= 4:
            after_yes(conn, d)
        else:
            if st == "confirmed":
                d["stage"] = "revising"
            changes = _revise(conn, llm, d, pdf, msg)
    else:
        transcript.bot(d, "busy")
    documents.save(conn, d)
    return d, changes


def _text_to_option(conn, d, msg):
    st = d["stage"]
    if st in ("identify", "duplicate", "save_ask"):
        if YES.match(msg):
            return "yes"
        if NO.match(msg):
            return "no"
    if st in ("identify", "pick", "pick_existing"):
        allp = profiles.list_all(conn)
        names = {p["name"].lower(): p["id"] for p in allp}
        low = msg.lower()
        for n, pid in names.items():
            if n in low:
                return f"profile:{pid}" if st != "identify" else ("yes" if pid == d.get("pending_profile_id") else f"profile:{pid}")
        close = difflib.get_close_matches(low, list(names), n=1, cutoff=0.6)
        if close:
            return f"profile:{names[close[0]]}"
        if st == "pick" and re.search(r"\bnew\b", low):
            return "new"
        if st == "identify":
            return "no"
    if st == "failed" and re.search(r"\b(retry|again|try)\b", msg, re.I):
        return "retry"
    return None


def _from_sheet_rows(o):
    # the model names rows by the sheet's numbers (1, 2, 3 ...); edits count from 0
    try:
        if o.get("op") == "set_cell":
            o = {**o, "row": int(o["row"]) - 1}
        elif o.get("op") == "drop_row":
            rows = o.get("rows") if isinstance(o.get("rows"), list) else [o.get("row")]
            o = {**o, "rows": [int(x) - 1 for x in rows]}
    except (TypeError, ValueError, KeyError):
        pass
    return o


def _from_sheet_letters(o, columns):
    # a column letter means the column the user saw under it when they sent the message
    names = {c.lower() for c in columns}
    by_letter = {chat_prompt.letter(i): c for i, c in enumerate(columns)}

    def name(ref):
        if not isinstance(ref, str) or ref.strip().lower() in names or not re.fullmatch(r"[A-Za-z]{1,2}", ref.strip()):
            return ref
        return by_letter.get(ref.strip().upper(), ref)

    o = {**o}
    if "col" in o:
        o["col"] = name(o["col"])
    # a place one past the last letter means "at the end"
    for key in ("at", "to"):
        if isinstance(o.get(key), str) and o[key].strip().upper() == chat_prompt.letter(len(columns)) and columns:
            o.pop(key)
            o["after"] = columns[-1]
    for key in ("at", "to", "after"):
        if key in o:
            o[key] = name(o[key])
    for key in ("cols", "order"):
        if isinstance(o.get(key), list):
            o[key] = [name(x) for x in o[key]]
    if o.get("op") == "add_row" and isinstance(o.get("values"), dict):
        o["values"] = {name(k): v for k, v in o["values"].items()}
    return o


def _revise(conn, llm, d, pdf, message):
    try:
        raw = llm.complete(pdf, chat_prompt.build(d, message), kind="chat")
    except Truncated:
        d["stage"] = "revising"
        transcript.bot(d, text="That reply got cut off before it finished, so nothing changed. Ask for a smaller change, "
                               "or ask me to re-read the columns from the PDF.")
        return []
    except LLMError as e:
        d["stage"] = "revising"
        transcript.bot(d, text=f"I couldn't process that: {e}. Try again, or edit the sheet directly.")
        return []
    reply = str((raw or {}).get("reply") or "").strip() or "Okay."
    intent = (raw or {}).get("intent") if (raw or {}).get("intent") in INTENTS else "edit"
    cols_now = [c["name"] for c in d["table"]["columns"]]
    op_list = [_from_sheet_letters(_from_sheet_rows(o), cols_now) for o in ((raw or {}).get("ops") or []) if isinstance(o, dict)]
    new_hints = [h for h in ((raw or {}).get("hints") or [])
                 if isinstance(h, dict) and h.get("text") and hint_rules.useful_hint(h.get("text"), cols_now)
                 and not hint_rules.about_order(h.get("text"))]

    if intent == "confirm" and not op_list:
        after_yes(conn, d)
        return []
    if intent == "reject" and not op_list:
        d["stage"] = "revising"
        transcript.bot(d, text=reply if reply.lower() != "okay." else dialogue.say("ask_changes"))
        return []
    if not op_list:
        ask_review(d, reply=reply, applied=False)
        return []

    return _apply_revision(conn, llm, d, pdf, reply, op_list, new_hints, message)
