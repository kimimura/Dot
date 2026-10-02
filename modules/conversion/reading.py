import config
from core import jobs, pdftext
from modules.documents import repository as documents
from modules.profiles import repository as profiles
from modules.reading import extract, layout, verify


def only_format_columns(table, prof):
    names = {c["name"] for c in prof["columns"]}
    cols = [c for c in table["columns"] if c["name"] in names]
    keep = {c["name"] for c in cols}
    return {"columns": cols, "rows": [{k: v for k, v in r.items() if k == "_doc" or k in keep} for r in table["rows"]]}


def ensure_layout(conn, prof):
    if prof.get("layout") is None:
        lay = None
        confirmed = [x for x in documents.docs_for_profile(conn, prof["id"]) if x.get("confirmed_at")][:config.LAYOUT_LEARN_FROM]
        for x in reversed(confirmed):
            d = documents.get(conn, x["id"])
            if d and d.get("table") and d["has_text_layer"]:
                lay = layout.add(lay, d["table"], pdftext.page_texts(documents.load_pdf(conn, d["id"])), d["id"])
        prof["layout"] = lay or {"variants": [], "learned_from": []}
        profiles.save(conn, prof)
    return prof["layout"]


def read_direct(conn, d, prof, texts):
    # Upload only: a known format is read straight from its learned layout; anything that doesn't fit goes to the model
    table, note = layout.read_table(ensure_layout(conn, prof), prof, texts)
    if table:
        ver = verify.verify(table, "\n\n".join(texts), True)
        bad = ver["total"] - ver["verified"]
        if not bad:
            return table, ver, None
        note = f"layout changed: {bad} value{'' if bad == 1 else 's'} didn't check out"
    return None, None, note


def read_with_model(llm, d, pdf, prof, texts):
    table, sig, _ = extract.run(llm, pdf, prof, texts=texts,
                                progress=lambda done, n: jobs.progress.__setitem__(d["id"], {"done": done, "of": n}))
    if prof:
        table = only_format_columns(table, prof)
    return table, verify.verify(table, "\n\n".join(texts), d["has_text_layer"]), sig
