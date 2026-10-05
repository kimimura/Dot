import copy
import json
import re

import pytest

import config
import pdfgen
from core import pdftext
from modules.reading import column_reread
from modules.reading.verify import norm_text

TARGETS = ["Total Qty.", "Unit Price (RM)"]


def items(k):
    return [pdfgen.econ_item(i["code"], i["bar"], i["desc"], i["unit"], i["pack"], str(int(i["qty"]) + k), f"{float(i['price']) + 0.01 * (k + 1):.4f}",
                             tail=i["tail"], desc_on_bar=i["on_bar"]) for i in pdfgen.ECON_A + pdfgen.ECON_B]


@pytest.fixture(scope="module")
def orders():
    return pdfgen.econsave([pdfgen.econ_po(f"100{k}-6126{k:06d}", f"100{k} S{k}", items(k)) for k in range(3)], per_page=4)


class Reader:
    # reads the asked columns from whichever pages it is given, like the real reader would
    def __init__(self, truth, garble=False):
        self.truth, self.garble, self.prompts = truth, garble, []

    def complete(self, pdf, prompt, kind="extract"):
        self.prompts.append(prompt)
        anchor = re.search(r'its "([^"]+)" exactly as printed, then (.+)\.\n', prompt)
        name, wanted = anchor.group(1), json.loads("[" + anchor.group(2) + "]")
        text = norm_text(pdftext.text_of(pdf))
        rows = [r for r in self.truth["rows"] if norm_text(r[name]) in text]
        rows.sort(key=lambda r: text.find(norm_text(r[name])))
        return {"rows": [["X" + r[name] if self.garble else r[name]] + [r[c] for c in wanted] for r in rows]}


def broken(truth):
    t = copy.deepcopy(truth)
    for r in t["rows"]:
        for c in TARGETS:
            r[c] = t["rows"][0][c]
    return t


def test_wrong_columns_are_read_again_from_the_pdf(orders):
    pdf, truth = orders
    reader = Reader(truth)
    table, changes, edited = column_reread.run(reader, pdf, broken(truth), TARGETS, set())
    assert [[r[c] for c in TARGETS] for r in table["rows"]] == [[r[c] for c in TARGETS] for r in truth["rows"]]
    assert changes == [{"ok": True, "text": f'Re-read "Total Qty.", "Unit Price (RM)" from the PDF ({len(truth["rows"])} of {len(truth["rows"])} rows)'}]
    assert edited == set() and all("Description" not in p.split("then", 1)[1] for p in reader.prompts)


def test_a_long_file_is_re_read_in_small_parts(orders, monkeypatch):
    pdf, truth = orders
    monkeypatch.setattr(config, "EXTRACT_CHUNK_CHARS", 900)
    reader = Reader(truth)
    table, _, _ = column_reread.run(reader, pdf, broken(truth), TARGETS, set())
    assert len(reader.prompts) > 1 and table["rows"] == truth["rows"]


def test_pages_where_the_reader_skipped_items_are_read_again_in_smaller_parts(orders):
    pdf, truth = orders

    class Lazy(Reader):
        def complete(self, pdf, prompt, kind="extract"):
            out = super().complete(pdf, prompt, kind)
            return {"rows": out["rows"][:3]} if pdftext.page_count(pdf) > 2 else out
    reader = Lazy(truth)
    table, changes, _ = column_reread.run(reader, pdf, broken(truth), TARGETS, set())
    assert table["rows"] == truth["rows"] and changes[0]["ok"] and len(reader.prompts) > 2


def test_cells_typed_by_hand_are_left_alone(orders):
    pdf, truth = orders
    t = broken(truth)
    t["rows"][3]["Unit Price (RM)"] = "my price"
    table, _, edited = column_reread.run(Reader(truth), pdf, t, TARGETS, {"3|Unit Price (RM)"})
    assert table["rows"][3]["Unit Price (RM)"] == "my price" and edited == {"3|Unit Price (RM)"}
    assert table["rows"][4]["Unit Price (RM)"] == truth["rows"][4]["Unit Price (RM)"]


def test_a_column_written_in_one_bulk_edit_is_re_read_in_full(orders):
    pdf, truth = orders
    whole = {f"{i}|{c}" for i in range(len(truth["rows"])) for c in TARGETS}
    table, changes, edited = column_reread.run(Reader(truth), pdf, broken(truth), TARGETS, whole | {"0|Description"})
    assert table["rows"] == truth["rows"] and edited == {"0|Description"} and changes[0]["ok"]


def test_a_re_read_that_does_not_line_up_changes_nothing(orders):
    pdf, truth = orders
    t = broken(truth)
    table, changes, _ = column_reread.run(Reader(truth, garble=True), pdf, t, TARGETS, set())
    assert table == t and not changes[0]["ok"] and "didn't line up" in changes[0]["text"]


def test_a_re_read_that_copies_another_column_changes_nothing(orders):
    pdf, truth = orders

    class WrongField(Reader):
        def complete(self, pdf, prompt, kind="extract"):
            name = re.search(r'its "([^"]+)"', prompt).group(1)
            return {"rows": [[r[name], r["Item Barcode"], r["Unit Price (RM)"]] for r in self.truth["rows"]]}
    t = broken(truth)
    table, changes, _ = column_reread.run(WrongField(truth), pdf, t, TARGETS, set())
    assert table == t and changes == [{"ok": False, "text": 'The re-read put "Item Barcode" values into "Total Qty.", so nothing changed'}]


def test_the_reader_is_shown_what_each_column_holds(orders):
    pdf, truth = orders
    reader = Reader(truth)
    column_reread.run(reader, pdf, broken(truth), TARGETS, set())
    assert json.dumps({c["name"]: truth["rows"][0][c["name"]] for c in truth["columns"]}, ensure_ascii=False)[:60] in reader.prompts[0]


def test_a_re_read_value_the_pdf_does_not_print_keeps_the_old_one(orders):
    pdf, truth = orders

    class Clipped(Reader):
        # leaves off the code printed under one description
        def complete(self, pdf, prompt, kind="extract"):
            return {"rows": [[x[0], x[1].replace(" 547309", "")] for x in super().complete(pdf, prompt, kind)["rows"]]}
    clipped = sum("547309" in r["Description"] for r in truth["rows"])
    t = copy.deepcopy(truth)
    t["rows"][0]["Description"] = "FC CLICK B-PEN"
    table, changes, _ = column_reread.run(Clipped(truth), pdf, t, ["Description"], set())
    assert table["rows"] == truth["rows"] and changes[0]["ok"]
    assert f"{clipped} cells left as they were because the new value doesn't match the PDF" in changes[0]["text"]


def test_a_re_read_that_cuts_many_values_short_is_still_refused(orders):
    pdf, truth = orders

    class Shortened(Reader):
        def complete(self, pdf, prompt, kind="extract"):
            out = super().complete(pdf, prompt, kind)["rows"]
            return {"rows": [[x[0], x[1].rsplit(" ", 1)[0] if k % 3 == 0 else x[1]] for k, x in enumerate(out)]}
    table, changes, _ = column_reread.run(Shortened(truth), pdf, copy.deepcopy(truth), ["Description"], set())
    assert table == truth and not changes[0]["ok"]


def test_a_re_read_that_matches_nothing_in_the_pdf_changes_nothing(orders):
    pdf, truth = orders

    class Typos(Reader):
        def complete(self, pdf, prompt, kind="extract"):
            return {"rows": [[x[0], x[1] + "Z"] for x in super().complete(pdf, prompt, kind)["rows"]]}
    table, changes, _ = column_reread.run(Typos(truth), pdf, copy.deepcopy(truth), ["Description"], set())
    assert table == truth and changes == [{"ok": False, "text": 'Nothing changed in "Description": the values that differed from the sheet don\'t match the PDF'}]


def test_an_unknown_column_changes_nothing(orders):
    pdf, truth = orders
    table, changes, _ = column_reread.run(Reader(truth), pdf, truth, ["Nope"], set())
    assert table == truth and changes == [{"ok": False, "text": 'No column called "Nope"'}]
