from core import jobs, pdftext
from core.ai.errors import LLMError
from modules.builder.review import ask_review
from modules.documents import repository as documents, transcript
from modules.profiles import repository as profiles
from modules.reading import extract, verify


def on_extract(conn, llm, d, pdf):
    prof = profiles.get(conn, d["profile_id"]) if d.get("profile_id") else None
    texts = pdftext.page_texts(pdf)
    try:
        table, sig, extra = extract.run(llm, pdf, prof, d.get("hints"), texts=texts,
                                        progress=lambda done, n: jobs.progress.__setitem__(d["id"], {"done": done, "of": n}))
    except LLMError as e:
        d["stage"], d["error"] = "failed", str(e)
        transcript.bot(d, "failed", error=str(e))
        documents.save(conn, d)
        return d
    finally:
        jobs.progress.pop(d["id"], None)
    d["table"], d["signature"], d["extra_fields"], d["error"] = table, sig, extra, None
    d["history"] = []
    d["verification"] = verify.verify(table, "\n\n".join(texts), d["has_text_layer"])
    ask_review(d, first=True)
    documents.save(conn, d)
    return d
