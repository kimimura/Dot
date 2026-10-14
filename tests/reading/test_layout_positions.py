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


def taught_brands(lay=None):
    pdf, sheet = pdfgen.smo_po(pdfgen.SMO_BRANDS)
    return layout.add(lay, sheet, pdftext.page_texts(pdf), "brands")


def test_codes_cut_out_of_different_brand_words_and_a_number_line_under_an_item_are_learned():
    lay = taught_brands()
    assert not lay.get("last_problem")
    v = lay["variants"][0]
    cols = {c["col"]: c for c in v["row"]}
    assert cols["Item Code"]["cut"] == {"prefix": ["FC-", "UHU-"]}
    assert cols["_after No"]["skip"] and cols["_after No"]["optional"] and v["skip_lines"] == ["INT:8"]
    pdf, sheet = pdfgen.smo_po(pdfgen.SMO_BRANDS)
    texts = pdftext.page_texts(pdf)
    table, note = layout.read_table(lay, PROFILE, texts)
    assert note is None and plain(table["rows"]) == plain(sheet["rows"])
    ver = verify.verify(table, "\n\n".join(texts), True)
    assert ver["verified"] == ver["total"]


def test_a_code_cut_out_of_a_brand_word_never_seen_is_cut_the_same_way():
    item = ("12-345-678", "289999990000", "STAEDTLER ERASER", "10.0000", "B0010", "1", "ctn", {"printed": "STA-12-345-678", "bare": True})
    pdf, want = pdfgen.smo_po([("HQ292399", "SMO Bookstores Raub", [pdfgen.SMO_BRANDS[1][2][0], item, pdfgen.SMO_BRANDS[1][2][3]])])
    table, note = layout.read_table(taught_brands(), PROFILE, pdftext.page_texts(pdf))
    assert note is None and [r["Item Code"] for r in table["rows"]] == ["187079", "12-345-678", "90-040-759"]


def test_a_confirmed_file_adds_to_the_layout_instead_of_standing_beside_it():
    lay = taught_brands(taught())
    assert not lay.get("last_problem") and len(lay["variants"]) == 1
    for orders in (pdfgen.SMO_NEW, pdfgen.SMO_BRANDS, pdfgen.SMO_TRAIN):
        pdf, want = pdfgen.smo_po(orders)
        table, note = layout.read_table(lay, PROFILE, pdftext.page_texts(pdf))
        assert note is None and plain(table["rows"]) == plain(want["rows"])
    # pieces, learned from the first file, next to brand codes, learned from the second, in one new file
    mixed = [("HQ292400", "SMO Bookstores Pekan", [pdfgen.SMO_NEW[0][2][0], pdfgen.SMO_BRANDS[0][2][2], pdfgen.SMO_BRANDS[0][2][3],
                                                   pdfgen.SMO_BRANDS[0][2][4]])]
    pdf, want = pdfgen.smo_po(mixed)
    table, note = layout.read_table(lay, PROFILE, pdftext.page_texts(pdf))
    assert note is None and plain(table["rows"]) == plain(want["rows"])


def test_a_cut_code_is_given_back_whole_from_the_pdf_for_every_row_without_a_model():
    from modules.reading import printed_words
    pdf, sheet = pdfgen.smo_po(pdfgen.SMO_BRANDS)
    text = "\n\n".join(pdftext.page_texts(pdf))
    table, changes, _ = printed_words.whole(sheet, "Item Code", text, set())
    assert [r["Item Code"] for r in table["rows"]] == ["FC-187054", "UHU-90-043-570", "97-033-510", "UHU-90-000-015", "UHU-90-036-355",
                                                      "FC-187079", "UHU-90-000-015", "97-033-515", "UHU-90-040-759"]
    assert changes[0]["text"] == 'Took "Item Code" as printed in full (7 of 9 rows)'
    ver = verify.verify(table, text, True)
    assert ver["verified"] == ver["total"]


def test_codes_kept_whole_as_printed_two_words_in_several_rows_are_learned_and_replace_an_old_cut():
    orders = pdfgen.SMO_BRANDS + [("HQ292283", "SMO Bookstores Pekan", [pdfgen.SMO_BRANDS[0][2][2], pdfgen.SMO_BRANDS[1][2][3]])]
    pdf, sheet = pdfgen.smo_po(orders)
    printed = [i[7].get("printed", f"FC-{i[0]}") if len(i) > 7 else f"FC-{i[0]}" for _, _, items in orders for i in items]
    for r, code in zip(sheet["rows"], printed):
        r["Item Code"] = code
    lay = layout.add(taught(), sheet, pdftext.page_texts(pdf), "whole")
    assert not lay.get("last_problem") and len(lay["variants"]) == 1
    cols = {c["col"]: c for c in lay["variants"][0]["row"]}
    assert "cut" not in cols["Item Code"] and set(cols["Item Code"]["seqs"]) == {"1", "2"}
    table, note = layout.read_table(lay, PROFILE, pdftext.page_texts(pdf))
    assert note is None and plain(table["rows"]) == plain(sheet["rows"])
    old, _ = pdfgen.smo_po(pdfgen.SMO_NEW)
    table, note = layout.read_table(lay, PROFILE, pdftext.page_texts(old))
    assert note is None and [r["Item Code"] for r in table["rows"]] == ["FC-178330", "FC-584803", "FC-100028295"]


def lost_item_po(at):
    # an item whose barcode prints as "N/A" opens no row the layout knows
    items = list(pdfgen.SMO_BRANDS[1][2][:3])
    items.insert(at, ("90-040-999", "N/A", "UHU NEW THING", "10.0000", "B0010", "1", "ctn", {"printed": "UHU-90-040-999"}))
    pdf, _ = pdfgen.smo_po([("HQ292401", "SMO Bookstores Raub", items)])
    return pdftext.page_texts(pdf)


def test_an_item_the_layout_can_t_read_at_either_end_of_a_po_stops_the_file_instead_of_going_missing():
    lay = taught_brands()
    table, note = layout.read_table(lay, PROFILE, lost_item_po(3))
    assert table is None and note.endswith('not found in 1 row')
    table, note = layout.read_table(lay, PROFILE, lost_item_po(0))
    assert table is None and note.endswith('not found in 1 row')


def test_a_file_with_one_po_confirmed_into_a_format_keeps_how_files_with_many_pos_are_split():
    one, sheet = pdfgen.smo_po(pdfgen.SMO_NEW)
    lay = layout.add(taught(), sheet, pdftext.page_texts(one), "one")
    assert lay["variants"][0]["split_by"] == "PO No."
    pdf, want = pdfgen.smo_po(pdfgen.SMO_TRAIN)
    table, note = layout.read_table(lay, PROFILE, pdftext.page_texts(pdf))
    assert note is None and plain(table["rows"]) == plain(want["rows"])


def test_a_column_renamed_on_the_profiles_page_is_still_read_under_its_new_name():
    lay = layout.rename(taught(), "Item Code", "Code")
    renamed = {"columns": [{**c, "name": "Code"} if c["name"] == "Item Code" else c for c in PROFILE["columns"]]}
    pdf, want = pdfgen.smo_po(pdfgen.SMO_NEW)
    table, note = layout.read_table(lay, renamed, pdftext.page_texts(pdf))
    assert note is None and [r["Code"] for r in table["rows"]] == [r["Item Code"] for r in want["rows"]]
