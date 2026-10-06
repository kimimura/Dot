from core import pdftext
from modules.documents import repository as documents


def store(conn, files, submission_id):
    # each PDF becomes a queued document of the submission, in the order it came; anything else is turned away with the reason
    ids, rejected = [], []
    position = len(documents.list_submission(conn, submission_id))
    for filename, data in files:
        if not filename.lower().endswith(".pdf"):
            rejected.append({"filename": filename, "error": "Not a PDF."})
            continue
        try:
            info = pdftext.inspect(data)
        except pdftext.PdfError as e:
            rejected.append({"filename": filename, "error": str(e)})
            continue
        d = documents.create(conn, filename, info, submission_id, stage="queued", position=position)
        documents.store_pdf(conn, d["id"], data)
        ids.append(d["id"])
        position += 1
    return ids, rejected
