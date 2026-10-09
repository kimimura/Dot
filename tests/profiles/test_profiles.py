from modules.conversion import convert, reading
from modules.profiles import hints as hint_rules, learning
from core import pdftext

ACME_COLS = [("Invoice No", "doc"), ("Date", "doc"), ("Item", "row"), ("Qty", "row")]


def doc_for(pdf):
    info = pdftext.inspect(pdf)
    return {"has_text_layer": info.has_text_layer, "tokens": info.tokens, "structural": info.structural}


def test_another_pdf_from_the_same_supplier_is_recognised(fake_db, acme_pdf, acme2_pdf, orbit_pdf):
    acme = fake_db.add_profile("ACME", ACME_COLS, acme_pdf)
    fake_db.add_profile("ORBIT", [("PO Number", "doc")], orbit_pdf)
    assert convert.possible_formats(None, doc_for(acme2_pdf)) == [acme["id"]]


def test_a_supplier_never_seen_before_is_new(fake_db, acme_pdf, orbit_pdf):
    fake_db.add_profile("ACME", ACME_COLS, acme_pdf)
    assert convert.possible_formats(None, doc_for(orbit_pdf)) == []


def test_two_formats_that_look_the_same_are_both_tried(fake_db, acme_pdf, acme2_pdf):
    a, b = fake_db.add_profile("ACME", ACME_COLS, acme_pdf), fake_db.add_profile("ACME OLD", ACME_COLS, acme_pdf)
    assert set(convert.possible_formats(None, doc_for(acme2_pdf))) == {a["id"], b["id"]}


def test_scans_are_never_matched(fake_db, acme_pdf):
    fake_db.add_profile("ACME", ACME_COLS, acme_pdf)
    assert convert.possible_formats(None, {"has_text_layer": False, "tokens": [], "structural": {}}) == []


def test_a_known_format_keeps_only_its_own_columns():
    table = {"columns": [{"name": "Invoice No", "kind": "doc"}, {"name": "Item", "kind": "row"}, {"name": "Surprise", "kind": "row"}],
             "rows": [{"_doc": 0, "Invoice No": "1", "Item": "A", "Surprise": "x"}]}
    out = reading.only_format_columns(table, {"columns": [{"name": "Invoice No"}, {"name": "Item"}]})
    assert [c["name"] for c in out["columns"]] == ["Invoice No", "Item"]
    assert out["rows"] == [{"_doc": 0, "Invoice No": "1", "Item": "A"}]


def test_renames_become_aliases_and_dropped_columns_stay_dropped():
    existing = [{"name": "Item Code", "kind": "row", "seen": 1}, {"name": "Department", "kind": "row", "seen": 1}]
    confirmed = [{"name": "Item Code 1", "kind": "row"}]
    hints = [{"scope": "col", "col": "Item Code 1", "alias": "Item Code", "text": "x"},
             {"scope": "col", "col": "Department", "dropped": True, "text": 'Do not extract "Department"'}]
    out = learning.merge_columns(existing, confirmed, hints)
    assert [(c["name"], c.get("aliases")) for c in out] == [("Item Code 1", ["Item Code"])]


def test_column_lists_are_not_kept_as_hints():
    cols = ["PO No", "Date", "Item Code", "Quantity"]
    assert hint_rules.useful_hint("Use the delivery date, not the order date", cols)
    assert not hint_rules.useful_hint("The columns are PO No, Date, Item Code and Quantity", cols)
    assert not hint_rules.useful_hint("PO No, Date, Item Code", cols)
    assert not hint_rules.useful_hint("", cols)
