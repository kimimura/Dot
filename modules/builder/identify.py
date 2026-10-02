from core import pdftext
from modules.documents import repository as documents, transcript
from modules.profiles import matching, repository as profiles


def on_upload(conn, pdf, filename):
    info = pdftext.inspect(pdf)
    d = documents.create(conn, filename, info)
    transcript.bot(d, "reading", filename=filename)
    dup = documents.by_sha(conn, info.sha256, exclude=d["id"])
    if dup:
        d["stage"] = "duplicate"
        d["duplicate_of"] = dup["id"]
        transcript.bot(d, "duplicate", filename=dup["filename"])
    else:
        if not d["has_text_layer"]:
            transcript.bot(d, "scanned_upfront")
        identify(conn, d)
    documents.save(conn, d)
    return d


def identify(conn, d, after_no=False):
    usable = [p for p in profiles.list_all(conn) if p["id"] not in d.get("rejected_profile_ids", [])]
    d["pending_profile_id"] = None
    if not d["has_text_layer"]:
        if usable:
            d["stage"], d["candidates"] = "pick", []
            transcript.bot(d, "pick_after_no" if after_no else "pick_scanned")
        else:
            d["stage"] = "extracting"
            transcript.bot(d, "extracting_fresh")
        return
    m = matching.match(d["tokens"], d["structural"], usable)
    d["candidates"] = m.get("candidates", [])
    if m["decision"] == "propose":
        d["stage"] = "identify"
        d["pending_profile_id"] = m["best"]["id"]
        transcript.bot(d, "propose" if m.get("strong") else "propose_weak", profile=m["best"]["name"])
    elif m["decision"] == "pick":
        d["stage"] = "pick"
        transcript.bot(d, "pick_after_no" if after_no else "pick")
    else:
        d["stage"] = "extracting"
        transcript.bot(d, "extracting_fresh" if after_no else "new_format")
