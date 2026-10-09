import pdfgen
from core import pdftext
from modules.builder import chat, chat_scope
from modules.reading import extract, verify
from reading.test_extract import PageReader


def long_doc():
    pdf, _ = pdfgen.purchase_orders(orders=2, pages_per_order=12, items_per_page=12)
    texts = pdftext.page_texts(pdf)
    table, _, _ = extract.run(PageReader(), pdf, texts=texts)
    d = {"table": table, "verification": verify.verify(table, "\n\n".join(texts), True), "hints": [], "stage": "review",
         "has_text_layer": True, "transcript": [], "history": [], "extra_fields": {}}
    return pdf, texts, d


def test_rows_named_in_a_message_are_found_in_any_wording():
    assert chat_scope.mentioned("row 72 and 73 are wrong", 100) == [71, 72]
    assert chat_scope.mentioned("check rows 10-12", 100) == [9, 10, 11]
    assert chat_scope.mentioned("lines 5, 7 too", 100) == [4, 6]
    assert chat_scope.mentioned("baris 3 salah", 100) == [2]
    assert chat_scope.mentioned("fix 72 please", 100) == []
    assert chat_scope.mentioned("row 500", 100) == []


def test_a_row_is_found_on_the_page_it_is_printed_on():
    _, texts, d = long_doc()
    shown, pages = chat_scope.pick(d, "row 40 is wrong", texts)
    assert 39 in shown and pages == [1, 4]


def test_the_chat_model_gets_only_the_pages_and_rows_the_message_is_about():
    pdf, texts, d = long_doc()
    seen = {}

    class Spy:
        def complete(self, part, prompt, kind="extract"):
            seen.update(pages=pdftext.page_count(part), prompt=prompt, kind=kind)
            return {"reply": "Okay.", "intent": "question", "ops": []}

    d["transcript"] = [{"who": "user", "text": "row 40 is wrong"}]
    chat._revise(None, Spy(), d, pdf, "row 40 is wrong")
    rows = len(d["table"]["rows"])
    assert seen["kind"] == "chat" and seen["pages"] == 2 and f"holds only pages 1, 4 of {len(texts)}" in seen["prompt"]
    assert "\n40 | " in seen["prompt"] and f"\n{rows} | " not in seen["prompt"] and "\n  ..." in seen["prompt"]


def test_values_for_many_rows_are_never_typed_by_the_chat_model_but_read_from_the_pdf():
    many, few = [str(i) for i in range(25)], ["1", "2"]
    assert chat.no_typing([{"op": "set_col", "col": "Qty", "values": many}]) == [{"op": "reread_cols", "cols": ["Qty"]}]
    assert chat.no_typing([{"op": "add_col", "name": "Store", "at": "B", "values": many}]) == [
        {"op": "add_col", "name": "Store", "at": "B"}, {"op": "reread_cols", "cols": ["Store"]}]
    assert chat.no_typing([{"op": "set_col", "col": "Qty", "values": few}]) == [{"op": "set_col", "col": "Qty", "values": few}]


def test_a_column_typed_out_by_the_chat_model_is_read_from_the_pdf_instead(monkeypatch):
    pdf, _, d = long_doc()
    before = [r["Description"] for r in d["table"]["rows"]]
    asked = []
    monkeypatch.setattr(chat.column_reread, "run", lambda llm, pdf, table, cols, edited, notes: (asked.append(cols), (table, [], edited))[1])
    typed = {"op": "set_col", "col": "Description", "values": ["typed"] * len(before)}
    chat._apply_revision(None, None, d, pdf, "Okay.", [typed], [], "fix the descriptions")
    assert asked == [["Description"]] and [r["Description"] for r in d["table"]["rows"]] == before
