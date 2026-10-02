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
