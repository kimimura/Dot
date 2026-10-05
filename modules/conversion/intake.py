from core import pdftext
from modules.documents import repository as documents


def store(conn, files, batch_id):
    # each PDF becomes a queued document in the batch; anything else is turned away with the reason
    ids, rejected = [], []
    for filename, data in files:
        if not filename.lower().endswith(".pdf"):
            rejected.append({"filename": filename, "error": "Not a PDF."})
            continue
        try:
            info = pdftext.inspect(data)
        except pdftext.PdfError as e:
            rejected.append({"filename": filename, "error": str(e)})
            continue
        d = documents.create(conn, filename, info, batch_id=batch_id, stage="queued")
        documents.store_pdf(conn, d["id"], data)
        ids.append(d["id"])
    return ids, rejected
