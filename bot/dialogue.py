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



def say(key, **ctx):
    return LINES[key].format(name=NAME, **ctx)

