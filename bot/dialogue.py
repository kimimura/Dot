import contextvars
import os

NAME = os.environ.get("COMPANION_NAME", "Dot").strip() or "Dot"

LINES = {
    "welcome": "Hi, I'm {name}. Drop a PDF on the left and I'll read it for you.",
    "reading": "Reading **{filename}**…",
    "new_format": "New one to me — I haven't seen this format before. Reading it fresh…",
    "propose": "This seems like it's **{profile}**, am I correct?",
    "propose_weak": "This might be **{profile}** — am I right?",
    "pick": "I'm not sure which format this is. Is it one of these?",
    "pick_scanned": "This looks like a scanned document, so I can't fingerprint it. Is it one of your saved formats?",
    "pick_after_no": "No problem. Is it one of these instead, or something new?",
    "extracting_with": "Got it. Reading it as **{profile}**…",
    "extracting_fresh": "Okay, reading it fresh…",
    "review": "This was all the fields I was able to extract. Is this the format you wanted?",
    "review_empty": "I couldn't find anything structured in there. Tell me what you're looking for and I'll try again.",
    "review_again": "{reply} Is this the format you wanted now?",
    "review_noop": "{reply} Anything else to change, or is this the format you wanted?",
    "ask_changes": "What are the fields you'd like to change?",
    "confirm_destructive": "Hold on — that would {what}. I haven't done it yet. Are you sure?",
    "cancelled": "Left it as it was. What would you like to change?",
    "extra_fields": "I also noticed {fields} — say the word if you want any of them in the table.",
    "save_ask": "Is this a new format? Would you like me to save it into Profiles?",
    "naming": "What should I call this format?",
    "name_taken": "You already have a profile called **{profile}**. Use that one, or pick a different name?",
    "saved_new": "Saved as **{profile}**. I'll recognize this format next time.",
    "saved_learned": "Saved. **{profile}** just got a little smarter.",
    "saved_only": "Saved to the Library.",
    "confirmed_done": "All done. Drop another PDF whenever you're ready.",
    "duplicate": "I've seen this exact file before — it's in the Library as **{filename}**. Read it again anyway?",
    "failed": "Something went wrong while reading: {error}. Want me to try again?",
    "busy": "Hold on, I'm still working on this one.",
    "scanned_note": "This is a scanned document, so I couldn't cross-check the values against the text.",
    "resume": "Welcome back. We were in the middle of **{filename}**.",
    "unsure_answer": "I'll take that as a change request.",
}


STARK = {
    "welcome": "Tony Stark. Well, a suit of him. Drop a PDF on the left and I'll have it taken apart before your coffee cools.",
    "reading": "Scanning **{filename}**. Running full diagnostics…",
    "new_format": "Never seen this layout before. New toy. Reverse-engineering it from scratch…",
    "propose": "Pretty sure this is **{profile}**. Am I right?",
    "propose_weak": "Could be **{profile}**. Not my most confident call. Am I right?",
    "pick": "Even a genius needs a hint. Is it one of these?",
    "pick_scanned": "It's a scan, so I can't fingerprint it. Is it one of your saved formats?",
    "pick_after_no": "Fine, I was wrong. Mark the date. One of these instead, or something new?",
    "extracting_with": "Copy that. Reading it as **{profile}**…",
    "extracting_fresh": "Starting from zero. My favourite kind of problem…",
    "review": "Here's everything I pulled out. Is this the format you wanted?",
    "review_empty": "Came up empty, which is rare for me. Tell me what you're after and I'll take another pass.",
    "review_again": "{reply} Is this the format you wanted now?",
    "review_noop": "{reply} Anything else to tweak, or is this the format you wanted?",
    "ask_changes": "Alright, talk to me. Which fields do you want changed?",
    "confirm_destructive": "Whoa, easy. That would {what}. I haven't touched it yet. You sure?",
    "cancelled": "Standing down, nothing changed. What do you want to adjust?",
    "extra_fields": "Also spotted {fields}. Say the word and they're in the table.",
    "save_ask": "New format. Want me to save it into Profiles? I'd call that an upgrade.",
    "naming": "Every suit needs a name. What do we call this format?",
    "name_taken": "You already have a profile called **{profile}**. Use that one, or pick a different name?",
    "saved_new": "Saved as **{profile}**. Next time I'll recognise it on sight.",
    "saved_learned": "Saved. **{profile}** just got an upgrade.",
    "saved_only": "Filed in the Library.",
    "confirmed_done": "Done. Too easy. Send the next one whenever you're ready.",
    "duplicate": "Déjà vu. I've already read this exact file, it's in the Library as **{filename}**. Read it again anyway?",
    "failed": "Well, that's a malfunction: {error}. Want me to try again?",
    "busy": "Hold your horses, I'm still working on this one.",
    "scanned_note": "It's a scan, so I couldn't cross-check the values against the text layer.",
    "resume": "Welcome back. We were in the middle of **{filename}**.",
    "unsure_answer": "I'll take that as a change request.",
}

# The browser sends the active avatar with every request (X-Avatar); app.py sets it per request.
PERSONAS = {
    "classic": {"lines": LINES, "speaker": NAME,
                "voice": f"You are {NAME}, a friendly assistant helping a user correct a spreadsheet extracted from the attached PDF.",
                "reply": "one or two short friendly sentences in first person describing what you did or answering"},
    "ironman": {"lines": STARK, "speaker": "Tony",
                "voice": "You are an assistant that speaks in the voice of Tony Stark (Iron Man): quick, confident, dry wit, "
                         "the occasional playful jab, never mean. Keep the swagger to a phrase or two; the user's request "
                         "always comes first and your answers must stay accurate. You are helping a user correct a "
                         "spreadsheet extracted from the attached PDF.",
                "reply": "one or two short sentences in first person, in Tony Stark's voice, describing what you did or answering"},
}
_persona = contextvars.ContextVar("persona", default="classic")


def set_persona(name):
    _persona.set(name if name in PERSONAS else "classic")


def persona():
    return PERSONAS[_persona.get()]


def say(key, **ctx):
    text = persona()["lines"].get(key) or LINES[key]
    return text.format(name=NAME, **ctx)

