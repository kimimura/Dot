import copy

import pytest

import pdfgen
from modules.reading import verify
from core import pdftext

COLUMNS = ["Item Code 1", "Description", "Warehouse", "Quantity", "UOM", "Unit Price", "Total", "Item Code 2", "Subtotal"]


@pytest.fixture(scope="module")
def text():
    return pdftext.text_of(pdfgen.becon())


def sheet():
    rows = []
    for code, desc, qty, uom, price, total, code2 in pdfgen.BECON_ITEMS:
        rows.append({"_doc": 0, "Item Code 1": code, "Description": " ".join(desc).replace("SO NIC", "SONIC"), "Warehouse": "PP001-00",
                     "Quantity": qty, "UOM": uom, "Unit Price": price, "Total": total, "Item Code 2": code2, "Subtotal": "MYR 3,216.46"})
    return {"columns": [{"name": c, "kind": "row"} for c in COLUMNS], "rows": rows}


def red(v):
    return sorted(k for k, s in v["cells"].items() if s == "elsewhere")


def swap(t, col, i, j):
    t = copy.deepcopy(t)
    t["rows"][i][col], t["rows"][j][col] = t["rows"][j][col], t["rows"][i][col]
    return t


def test_a_correct_sheet_has_no_red_cells(text):
    v = verify.verify(sheet(), text, True)
    assert red(v) == [] and v["verified"] == v["total"]


@pytest.mark.parametrize("col", ["Item Code 1", "Description", "Unit Price", "Total", "Item Code 2"])
def test_values_swapped_between_neighbouring_rows_turn_red(text, col):
    v = verify.verify(swap(sheet(), col, 1, 2), text, True)
    assert red(v) == [f"1|{col}", f"2|{col}"]
    assert v["verified"] == v["total"] - 2


def test_the_second_code_printed_under_a_row_belongs_to_that_row(text):
    t = sheet()
    t["rows"][0]["Item Code 2"] = "90000065"
    assert red(verify.verify(t, text, True)) == ["0|Item Code 2"]


def test_values_printed_once_for_the_whole_document_are_left_alone(text):
    v = verify.verify(sheet(), text, True)
    assert all(v["cells"][f"{i}|Subtotal"] == "ok" for i in range(len(pdfgen.BECON_ITEMS)))


def test_a_unit_mix_up_is_caught_too(text):
    v = verify.verify(swap(sheet(), "UOM", 0, 2), text, True)
    assert red(v) == ["0|UOM", "2|UOM"]


def test_a_value_missing_from_the_pdf_stays_orange_not_red(text):
    t = sheet()
    t["rows"][1]["Total"] = "999.99"
    v = verify.verify(t, text, True)
    assert v["cells"]["1|Total"] == "miss" and red(v) == []


def test_a_cell_typed_by_hand_is_never_red(text):
    v = verify.verify(swap(sheet(), "Total", 1, 2), text, True, edited={"1|Total", "2|Total"})
    assert red(v) == [] and v["cells"]["1|Total"] == "edited"


def test_document_fields_are_not_checked_for_rows(text):
    t = sheet()
    t["columns"].insert(0, {"name": "PO", "kind": "doc"})
    for r in t["rows"]:
        r["PO"] = "231020"
    assert red(verify.verify(t, text, True)) == []


def test_scans_are_not_checked():
    v = verify.verify(swap(sheet(), "Total", 1, 2), "", False)
    assert red(v) == [] and v["checked"] is False


def repeated_items(k):
    # the same products in every order, each order at its own prices: only the price line tells the rows apart
    return [pdfgen.econ_item(i["code"], i["bar"], i["desc"], i["unit"], i["pack"], i["qty"], f"{float(i['price']) + 0.01 * (k + 1) + 0.1 * n:.4f}",
                             tail=i["tail"], desc_on_bar=i["on_bar"]) for n, i in enumerate(pdfgen.ECON_A + pdfgen.ECON_B)]


@pytest.fixture(scope="module")
def orders():
    pdf, truth = pdfgen.econsave([pdfgen.econ_po(f"100{k}-6126{k:06d}", f"100{k} S{k}", repeated_items(k)) for k in range(4)], per_page=4)
    return pdftext.text_of(pdf), truth


def test_rows_found_by_their_price_line_are_not_red(orders):
    text, truth = orders
    assert red(verify.verify(truth, text, True)) == []


def test_codes_swapped_in_such_a_file_are_still_red(orders):
    text, truth = orders
    assert "2|Item Barcode" in red(verify.verify(swap(truth, "Item Barcode", 1, 2), text, True))


def test_a_document_field_left_empty_on_some_of_its_pages_is_missing():
    cols = [{"name": "PO", "kind": "doc"}, {"name": "Total", "kind": "doc"}, {"name": "Item", "kind": "row"}]
    rows = [{"_doc": 0, "PO": "PO-1", "Total": "", "Item": "A100"}, {"_doc": 1, "PO": "PO-1", "Total": "99.00", "Item": "B200"},
            {"_doc": 2, "PO": "PO-2", "Total": "", "Item": "C300"}]
    v = verify.verify({"columns": cols, "rows": rows}, "PO-1 A100 B200 99.00 PO-2 C300", True)
    assert v["cells"]["0|Total"] == "blank" and v["cells"]["2|Total"] == "na"
    assert (v["verified"], v["total"]) == (7, 8)


def yellow(v):
    return sorted(k for k, s in v["cells"].items() if s == "miss")


def wrapped_items(k):
    # one code wraps onto the top of the next page, and one amount runs past a thousand
    items = pdfgen.ECON_A[:3] + [pdfgen.econ_item("543000136", "9555684635143", "FC GRIP X7 BPEN-R 0.7MM BLUE 3S", "1UNITx1", "1.00", "10", "3.5900",
                                                  tail="547405", tail_next_page=True)] + pdfgen.ECON_B + \
            [pdfgen.econ_item("543710032", "9555684690418", "FC DF ERASER SIZE 20 WHITE 187020", "1 UNIT", "40.00", "400", "3.0600")]
    return [{**i, "price": f"{float(i['price']) + 0.01 * (k + 1) + 0.1 * n:.4f}"} for n, i in enumerate(items)]


@pytest.fixture(scope="module")
def wrapped():
    orders = [pdfgen.econ_po(f"200{k}-7126{k:06d}", f"200{k} W{k}", wrapped_items(k)) for k in range(3)]
    for o in orders:
        for i in o["items"]:
            i["amount"] = f"{float(i['qty']) * float(i['price']):,.2f}"
    pdf, truth = pdfgen.econsave(orders, per_page=4)
    return pdftext.text_of(pdf), truth


def test_a_correct_sheet_with_wrapped_codes_has_no_marks(wrapped):
    text, truth = wrapped
    v = verify.verify(truth, text, True)
    assert yellow(v) == [] and red(v) == [] and v["verified"] == v["total"]


@pytest.mark.parametrize("was, now", [("BPEN-R0.5MMBLK", "B-PEN-R0.5MMBLK"), ("ERASER SIZE 48", "ERASE SIZE 48"),
                                      (" 547309", ""), (" 547405", ""), (" 187049", "")])
def test_a_value_not_printed_exactly_like_that_is_yellow(wrapped, was, now):
    text, truth = wrapped
    t = copy.deepcopy(truth)
    i = next(i for i, r in enumerate(t["rows"]) if was in r["Description"])
    t["rows"][i]["Description"] = t["rows"][i]["Description"].replace(was, now)
    assert yellow(verify.verify(t, text, True)) == [f"{i}|Description"]


def test_orders_that_repeat_exactly_are_still_checked_row_by_row():
    orders = [pdfgen.econ_po(f"200{k}-7126{k:06d}", f"200{k} W{k}", wrapped_items(0)) for k in range(3)]
    pdf, truth = pdfgen.econsave(orders, per_page=4)
    text = pdftext.text_of(pdf)
    assert yellow(verify.verify(truth, text, True)) == [] and red(verify.verify(truth, text, True)) == []
    t = copy.deepcopy(truth)
    t["rows"][10]["Description"] = t["rows"][10]["Description"].replace(" 547309", "")
    assert yellow(verify.verify(t, text, True)) == ["10|Description"]


@pytest.mark.parametrize("pdf, ok", [("Board Marker W20 -\nBlack (254099)", True), ("Board Marker W20\n- Black (254099)", True),
                                     ("Board Marker W20\nBlack (254099)", False), ("Board Marker W20 -\nBlue (254099)", False)])
def test_a_separator_may_end_one_line_or_start_the_next_when_a_value_wraps(pdf, ok):
    lines = verify.strict_lines("9 1480521-01 Faber-Castell White " + pdf + "\nPP001-00 80 PCS 1.3900")
    assert verify.printed("Faber-Castell White Board Marker W20 - Black (254099)", lines) is ok


def test_separators_the_pdf_prints_may_be_left_out(wrapped):
    text, truth = wrapped
    t = copy.deepcopy(truth)
    i = next(i for i, r in enumerate(t["rows"]) if "," in r["Amount (RM)"])
    t["rows"][i]["Amount (RM)"] = t["rows"][i]["Amount (RM)"].replace(",", "")
    assert yellow(verify.verify(t, text, True)) == [] and red(verify.verify(t, text, True)) == []
