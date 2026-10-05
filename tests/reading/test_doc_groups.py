from modules.reading import doc_groups, extract

COLS = [{"name": "PO", "kind": "doc"}, {"name": "Page", "kind": "doc"}, {"name": "Grand Total", "kind": "doc"}, {"name": "Item", "kind": "row"}]


def page(doc, po, n, total, items):
    return [{"_doc": doc, "PO": po, "Page": f"{n} of 2", "Grand Total": total, "Item": i} for i in items]


def test_pages_of_one_order_read_on_their_own_become_one_order_again():
    rows = page(0, "PO-1", 1, "", ["A", "B"]) + page(1, "PO-1", 2, "50.00", ["C"]) + page(2, "PO-2", 1, "9.00", ["D"])
    t = doc_groups.join_pages({"columns": COLS, "rows": rows})
    assert [r["_doc"] for r in t["rows"]] == [0, 0, 0, 1]
    assert [r["Grand Total"] for r in t["rows"]] == ["50.00", "50.00", "50.00", "9.00"]
    assert [r["Page"] for r in t["rows"]] == ["1 of 2", "1 of 2", "2 of 2", "1 of 2"]


def test_different_orders_next_to_each_other_stay_apart():
    rows = page(0, "PO-1", 1, "", ["A"]) + page(1, "PO-2", 1, "9.00", ["B"])
    t = doc_groups.join_pages({"columns": COLS, "rows": rows})
    assert [(r["_doc"], r["Grand Total"]) for r in t["rows"]] == [(0, ""), (1, "9.00")]


def test_one_document_is_left_as_it_is():
    rows = page(0, "PO-1", 1, "", ["A", "B"])
    assert doc_groups.join_pages({"columns": COLS, "rows": rows})["rows"] == rows


def test_reading_a_file_joins_its_pages(monkeypatch):
    class Reader:
        def complete(self, pdf, prompt, kind="extract"):
            return {"documents": [{"document_fields": {"PO": "PO-7", "Grand Total": ""}, "row_columns": ["Item"], "rows": [["A"], ["B"]]},
                                  {"document_fields": {"PO": "PO-7", "Grand Total": "80.00"}, "row_columns": ["Item"], "rows": [["C"]]}]}
    table, _, _ = extract.run(Reader(), b"%PDF", texts=["page one text " * 5])
    assert {r["_doc"] for r in table["rows"]} == {0} and {r["Grand Total"] for r in table["rows"]} == {"80.00"}
