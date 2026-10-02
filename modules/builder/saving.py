from core import db, pdftext
from modules.documents import repository as documents, transcript
from modules.profiles import learning, repository as profiles
from modules.reading import layout


def after_yes(conn, d):
    if d.get("profile_id"):
        confirm(conn, d, profile_id=d["profile_id"])
    else:
        d["stage"] = "save_ask"
        transcript.bot(d, "save_ask")


def confirm(conn, d, profile_id=None, new_name=None):
    prof = None
    if new_name:
        existing = profiles.by_name(conn, new_name)
        if existing:
            d["stage"], d["pending_name"] = "naming", existing["name"]
            transcript.bot(d, "name_taken", profile=existing["name"])
            return
        doc_cols = [{"name": c["name"], "kind": c.get("kind", "row"), "seen": 0, "hint": ""} for c in d["table"]["columns"]]
        prof = profiles.create(conn, new_name, doc_cols, d.get("signature"))
    elif profile_id:
        prof = profiles.get(conn, profile_id)
    if prof:
        if d["has_text_layer"]:
            try:
                texts = pdftext.page_texts(documents.load_pdf(conn, d["id"]))
            except Exception:
                texts = None
            if texts:
                prof["layout"] = layout.add(prof.get("layout"), d["table"], texts, d["id"])
        learning.learn(conn, prof, d, d["table"], d.get("hints", []), d.get("tokens"), d.get("structural"), d.get("signature"))
        d["profile_id"] = prof["id"]
    d["stage"], d["confirmed_at"], d["pending_name"], d["read_note"] = "confirmed", db.now(), None, None
    if new_name and prof:
        transcript.bot(d, "saved_new", profile=prof["name"])
    elif prof:
        transcript.bot(d, "saved_learned", profile=prof["name"])
    else:
        transcript.bot(d, "saved_only")
