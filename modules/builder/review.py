from modules.companion import dialogue
from modules.documents import transcript


def ask_review(d, first=False, reply=None, applied=True):
    if not d["table"]["columns"]:
        d["stage"] = "revising"
        transcript.bot(d, "review_empty")
        return
    d["stage"] = "review"
    if reply:
        text = dialogue.say("review_again" if applied else "review_noop", reply=reply.rstrip() if reply.rstrip().endswith((".", "!", "?")) else reply.rstrip() + ".")
    else:
        text = dialogue.say("review")
        if not d["has_text_layer"]:
            text = dialogue.say("scanned_note") + " " + text
        if first and d.get("extra_fields"):
            names = ", ".join(f"**{k}**" for k in list(d["extra_fields"])[:4])
            text += " " + dialogue.say("extra_fields", fields=names)
    transcript.bot(d, text=text)
