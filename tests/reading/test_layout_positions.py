import copy

import pdfgen
from core import pdftext
from modules.reading import layout, verify
from modules.reading.layout_learn import learn
from modules.reading.layout_places import Unlearnable

PROFILE = {"columns": [{"name": n, "kind": k} for n, k in pdfgen.SMO_COLUMNS]}


def taught():
    pdf, sheet = pdfgen.smo_po(pdfgen.SMO_TRAIN)
    return layout.add(None, sheet, pdftext.page_texts(pdf), "teach")


def plain(rows):
    return [{k: v for k, v in r.items() if k != "_doc"} for r in rows]


def test_items_numbered_above_with_cut_codes_and_side_by_side_quantities_are_learned():
    lay = taught()
    assert not lay.get("last_problem")
    cols = {c["col"]: c for c in lay["variants"][0]["row"]}
    assert cols["No"]["seqs"] == {"1": [["INT:1-3"]]} and cols["Item Code"]["cut"] == {"prefix": "FC-"}
    assert cols["Qty Ctn"]["spot"] < cols["Qty Pcs"]["spot"] and cols["Qty Ctn"]["alt"] == cols["Qty Pcs"]["alt"]
    assert cols["Qty Ctn"]["between"] == ["UOM", "Gross Amount"]


def test_a_new_file_is_read_with_each_quantity_under_the_column_it_is_printed_beneath():
    pdf, want = pdfgen.smo_po(pdfgen.SMO_NEW)
    texts = pdftext.page_texts(pdf)
    table, note = layout.read_table(taught(), PROFILE, texts)
    assert note is None and plain(table["rows"]) == plain(want["rows"])
    assert [(r["Qty Ctn"], r["Qty Pcs"]) for r in table["rows"]] == [("", "3"), ("6", ""), ("7", "")]
    ver = verify.verify(table, "\n\n".join(texts), True)
    assert ver["verified"] == ver["total"]


def test_a_sheet_with_quantities_under_the_wrong_column_is_refused_and_says_where():
    pdf, sheet = pdfgen.smo_po(pdfgen.SMO_TRAIN)
    wrong = copy.deepcopy(sheet)
    for r in wrong["rows"]:
        if r["Qty Ctn"]:
            r["Qty Ctn"], r["Qty Pcs"] = "", r["Qty Ctn"]
    try:
        learn(wrong, pdftext.page_texts(pdf))
        raise AssertionError("learned from a sheet the PDF contradicts")
    except Unlearnable as e:
        assert str(e) == '"Qty Pcs" values are printed under two different columns on the PDF: check the sheet'


def test_a_quantity_printed_under_a_column_never_taught_sends_the_file_to_the_model():
    only_pieces = [(po, store, [i for i in items if i[-1] == "pcs"]) for po, store, items in pdfgen.SMO_TRAIN]
    pdf, sheet = pdfgen.smo_po(only_pieces)
    lay = layout.add(None, sheet, pdftext.page_texts(pdf), "teach")
    new, _ = pdfgen.smo_po(pdfgen.SMO_NEW)
    table, note = layout.read_table(lay, PROFILE, pdftext.page_texts(new))
    assert table is None and note == 'layout changed: "Qty Pcs" printed under a different column'


def test_without_word_positions_a_file_is_not_guessed_but_left_to_the_model():
    pdf, _ = pdfgen.smo_po(pdfgen.SMO_NEW)
    texts = [str(t) for t in pdftext.page_texts(pdf)]
    table, note = layout.read_table(taught(), PROFILE, texts)
    assert table is None and "positions" in note


def test_a_document_s_own_number_never_counts_as_a_printed_value():
    row = {"_doc": 11, "SKU Description": "381811 FC DESKTOP SHARPENER PLUS", "Unit Price": "17.6000", "UOM": "PCS",
           "Qty Pcs": "1", "Gross Amount": "17.60", "Nett Amount": "17.60"}
    line = verify.norm_text("381811 FC DESKTOP SHARPENER PLUS 17.6000 PCS 1 17.60 17.60")
    assert verify._rest_of_line(row, "SKU Description", [line]) == ""


def taught_with_a_wrapped_store():
    pdf, sheet = pdfgen.smo_po(pdfgen.SMO_TRAIN + pdfgen.SMO_WRAPPED)
    return layout.add(None, sheet, pdftext.page_texts(pdf), "teach")


def stores(orders, lay=None):
    pdf, _ = pdfgen.smo_po(orders)
    table, note = layout.read_table(lay or taught_with_a_wrapped_store(), PROFILE, pdftext.page_texts(pdf))
    assert note is None
    return [r["Store Code"] for r in table["rows"]]


ITEM = [("178318", "281485130000", "FABER-CASTELL 18CM STRAIGHT RULER", "29.2800", "B0020", "1", "ctn")]


def test_a_store_name_the_pdf_wraps_onto_a_second_line_is_read_whole():
    assert taught_with_a_wrapped_store()["variants"][0]["fields"]["Store Code"]["wrap"]["stops"] == ["Unit"]
    assert stores([("HQ292391", ("SMO Bookstores Kota Bharu Kompleks", "Mutiara"), ITEM)]) == ["SMO Bookstores Kota Bharu Kompleks Mutiara"]


def test_the_line_under_a_store_name_stays_out_when_it_opens_the_address_or_would_have_fitted():
    assert stores([("HQ292392", "SMO Bookstores Kota Bharu Kompleks Mutiara", ITEM)]) == ["SMO Bookstores Kota Bharu Kompleks Mutiara"]
    assert stores([("HQ292393", "SMO Bookstores Raub", ITEM, "Jalan Besar 3,")]) == ["SMO Bookstores Raub"]


def test_a_sheet_without_wrapped_names_never_joins_lines():
    assert "wrap" not in taught()["variants"][0]["fields"]["Store Code"]
    assert stores([("HQ292394", ("SMO Bookstores Kota Bharu Kompleks", "Mutiara"), ITEM)], taught()) == ["SMO Bookstores Kota Bharu Kompleks"]
