import copy

import pytest

import pdfgen
from core import pdftext
from modules.reading import from_text, verify
from test_verify import wrapped_items


@pytest.fixture(scope="module")
def orders():
    pos = [pdfgen.econ_po(f"200{k}-7126{k:06d}", f"200{k} W{k}", wrapped_items(k)) for k in range(3)]
    for o in pos:
        for i in o["items"]:
            i["amount"] = f"{float(i['qty']) * float(i['price']):,.2f}"
    pdf, truth = pdfgen.econsave(pos, per_page=4)
    return pdftext.text_of(pdf), truth


def broken(truth, changes):
    t = copy.deepcopy(truth)
    for was, now in changes:
        i = next(i for i, r in enumerate(t["rows"]) if was in r["Description"])
        t["rows"][i]["Description"] = t["rows"][i]["Description"].replace(was, now)
    return t


def fixed(text, t, cols=("Description",), edited=()):
    return from_text.fix(t, text, verify.verify(t, text, True)["cells"], list(cols), set(edited))


def test_cells_that_do_not_match_take_the_text_the_pdf_prints(orders):
    text, truth = orders
    t = broken(truth, [("BPEN-R0.5MMBLK", "B-PEN-R0.5MMBLK"), ("ERASER SIZE 48", "ERASE SIZE 48"), (" 547309", ""), (" 547405", "")])
    table, n = fixed(text, t)
    assert table["rows"] == truth["rows"] and n == 4


def test_cells_spaced_differently_from_the_pdf_take_its_spacing(orders):
    text, truth = orders
    t = broken(truth, [("BPEN-R0.5MMBLK 4S", "BPEN-R 0.5MM BLK 4S"), ("0.5MM2BL/1BK 3S 547309", "0.5MM 2BL/1BK 3S 547309"), ("ERASER-", "ERASER -")])
    table, n = fixed(text, t)
    assert table["rows"] == truth["rows"] and n == 3


def test_a_sheet_already_spaced_like_the_pdf_is_left_as_it_is(orders):
    text, truth = orders
    assert fixed(text, truth) == (truth, 0)


def test_a_cell_with_no_close_text_in_the_pdf_is_left_alone(orders):
    text, truth = orders
    t = broken(truth, [("FC GRIP X5 BPEN-R0.5MM2BL/1BK 3S 547309", "something else entirely")])
    table, n = fixed(text, t)
    assert table == t and n == 0


@pytest.mark.parametrize("printed, want", [(["RED PEN"], "RED PEN"), (["RED PEN", "RED PIN"], "RED PAN")])
def test_two_equally_close_texts_leave_the_cell_alone(printed, want):
    cols = [{"name": "Item", "kind": "row"}, {"name": "Note", "kind": "row"}]
    t = {"columns": cols, "rows": [{"_doc": 0, "Item": "A100", "Note": "RED PAN"}, {"_doc": 0, "Item": "B200", "Note": "BLUE CAP"}]}
    text = "\n".join(["A100"] + printed + ["B200", "BLUE CAP"])
    assert fixed(text, t, cols=["Note"])[0]["rows"][0]["Note"] == want


@pytest.mark.parametrize("printed, want", [(["REDPEN"], "REDPEN"), (["RED PEN", "REDPEN"], "RE DPEN")])
def test_two_spacings_of_the_same_text_leave_the_cell_alone(printed, want):
    cols = [{"name": "Item", "kind": "row"}, {"name": "Note", "kind": "row"}]
    t = {"columns": cols, "rows": [{"_doc": 0, "Item": "A100", "Note": "RE DPEN"}, {"_doc": 0, "Item": "B200", "Note": "BLUE CAP"}]}
    text = "\n".join(["A100"] + printed + ["B200", "BLUE CAP"])
    assert fixed(text, t, cols=["Note"])[0]["rows"][0]["Note"] == want


def test_only_the_asked_columns_and_cells_not_typed_by_hand_change(orders):
    text, truth = orders
    t = broken(truth, [(" 547309", "")])
    i = next(i for i, r in enumerate(t["rows"]) if r["Description"] != truth["rows"][i]["Description"])
    assert fixed(text, t, cols=["Amount (RM)"]) == (t, 0)
    assert fixed(text, t, edited=[f"{i}|Description"]) == (t, 0)
