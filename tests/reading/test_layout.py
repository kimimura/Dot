import copy
import io

import pytest

import pdfgen
from modules.builder import saving
from modules.conversion import reading
from modules.reading import layout, layout_learn, layout_places, layout_read, layout_tokens
from core import ai as llm, db, pdftext


@pytest.fixture(scope="module")
def trained():
    pdf, sub = pdfgen.becon_po(pdfgen.TRAIN_ITEMS, po="231020", per_page=4)
    sheet = pdfgen.becon_sheet(pdfgen.TRAIN_ITEMS, "231020", sub)
    return pdf, sheet, layout.add(None, sheet, pdftext.page_texts(pdf), "train")


def read(lay, items, **kw):
    pdf, sub = pdfgen.becon_po(items, **kw)
    prof = {"columns": [{"name": n, "kind": k} for n, k in pdfgen.PO_COLUMNS]}
    table, note = layout.read_table(lay, prof, pdftext.page_texts(pdf))
    return table, note, pdfgen.becon_sheet(items, kw.get("po", "231020"), sub)


class Counting:
    def __init__(self):
        self.calls = 0

    def complete(self, pdf, prompt, kind="extract"):
        self.calls += 1
        return llm.OfflineAdapter().complete(pdf, prompt, kind)


# ── learning and reading ─────────────────────────────────────────────────────

def test_a_confirmed_sheet_is_learned(trained):
    _, _, lay = trained
    v = lay["variants"][0]
    assert "last_problem" not in lay and v["lead"] == 2
    assert [c["col"] for c in v["row"]] == ["Item No.", "Item Code 1", "Description", "SKU", "Quantity", "UOM",
                                            "Unit Price (MYR)", "Total Excl. Tax (MYR)", "Item Code 2"]


def test_a_new_file_of_the_same_format_is_read_exactly(trained):
    table, note, want = read(trained[2], pdfgen.NEW_ITEMS, po="231019", per_page=3)
    assert note is None
    assert table == want


def test_labels_pick_the_right_one_of_two_similar_dates(trained):
    table, _, _ = read(trained[2], pdfgen.NEW_ITEMS[:2], po="231030")
    assert (table["rows"][0]["Date"], table["rows"][0]["Delivery Date"]) == ("15.09.26", "14.09.26")


def test_a_long_word_broken_over_two_lines_is_joined_back(trained):
    table, _, _ = read(trained[2], pdfgen.NEW_ITEMS, po="231019", per_page=3)
    assert table["rows"][5]["Description"] == "UHU Glue Stic 21g ReNATURE/MINECRAFT/MONSTER/SONIC"


def test_a_date_learned_from_a_file_where_both_dates_match_still_reads_the_right_label():
    pdf, sub = pdfgen.becon_po(pdfgen.TRAIN_ITEMS, date="14.09.26")
    lay = layout.add(None, pdfgen.becon_sheet(pdfgen.TRAIN_ITEMS, "231020", sub, date="14.09.26"), pdftext.page_texts(pdf), "t")
    table, _, _ = read(lay, pdfgen.NEW_ITEMS[:2], date="20.09.26")
    assert (table["rows"][0]["Date"], table["rows"][0]["Delivery Date"]) == ("20.09.26", "14.09.26")


def test_broken_words_are_rejoined_even_when_the_teaching_file_had_none():
    items = pdfgen.TRAIN_ITEMS[1:]
    pdf, sub = pdfgen.becon_po(items)
    lay = layout.add(None, pdfgen.becon_sheet(items, "231020", sub), pdftext.page_texts(pdf), "t")
    table, _, _ = read(lay, pdfgen.NEW_ITEMS)
    assert table["rows"][5]["Description"] == "UHU Glue Stic 21g ReNATURE/MINECRAFT/MONSTER/SONIC"


def test_documents_that_cannot_be_told_apart_are_not_learned():
    sheet = pdfgen.becon_sheet(pdfgen.TRAIN_ITEMS, "100001", "0")
    sheet["rows"][-1].update(_doc=1, **{"PO No.": "100002"})
    with pytest.raises(layout_places.Unlearnable, match="couldn't tell the documents"):
        layout_learn.learn(sheet, ["x"])


# ── when the file doesn't fit, say exactly why ───────────────────────────────

def test_a_new_column_in_the_header_is_named(trained):
    table, note, _ = read(trained[2], pdfgen.NEW_ITEMS, header_extra="Discount")
    assert table is None and note == 'header changed: new column "Discount"'


def test_a_value_missing_from_some_rows_is_named(trained):
    items = copy.deepcopy(pdfgen.NEW_ITEMS)
    items[1]["code2"] = None
    table, note, _ = read(trained[2], items)
    assert table is None and note == 'layout changed: "Item Code 2" not found in 1 row'


def test_a_new_column_is_never_read_silently_into_another_one(trained):
    pdf, _ = pdfgen.becon_po(pdfgen.NEW_ITEMS, header_extra="Discount")
    text = pdftext.page_texts(pdf)
    variant = copy.deepcopy(trained[2]["variants"][0])
    variant["header"] = []
    rows, why = layout_read.read_variant(variant, text)
    assert rows is None and why.startswith("layout changed:")


def test_unexpected_lines_between_rows_are_counted(trained):
    table, note, _ = read(trained[2], pdfgen.NEW_ITEMS[:3], stray_after=0)
    assert table is None and note == "layout changed: 1 line between rows weren't understood"


def test_a_stray_number_between_rows_is_not_taken_for_page_noise(trained):
    table, note, _ = read(trained[2], pdfgen.NEW_ITEMS, per_page=3, stray_after=1, stray="999999")
    assert table is None and note == "layout changed: 1 line between rows weren't understood"


def test_a_column_added_to_the_format_after_learning_is_named(trained):
    pdf, _ = pdfgen.becon_po(pdfgen.NEW_ITEMS)
    prof = {"columns": [{"name": n, "kind": k} for n, k in pdfgen.PO_COLUMNS] + [{"name": "Discount", "kind": "row"}]}
    assert layout.read_table(trained[2], prof, pdftext.page_texts(pdf)) == (None, 'layout not learned for "Discount" yet')


def test_a_renamed_column_is_found_through_its_old_name(trained):
    pdf, _ = pdfgen.becon_po(pdfgen.NEW_ITEMS)
    cols = [{"name": n, "kind": k} for n, k in pdfgen.PO_COLUMNS]
    cols[11] = {"name": "Qty", "kind": "row", "aliases": ["Quantity"]}
    table, note = layout.read_table(trained[2], {"columns": cols}, pdftext.page_texts(pdf))
    assert note is None and table["rows"][0]["Qty"] == "90"


# ── in the app ───────────────────────────────────────────────────────────────

def becon_profile(fake_db, trained):
    pdf, sheet, lay = trained
    p = fake_db.add_profile("BECON", pdfgen.PO_COLUMNS, pdf)
    p["layout"] = copy.deepcopy(lay)
    return p


def test_upload_reads_a_known_format_without_the_model(client, fake_db, trained, monkeypatch):
    becon_profile(fake_db, trained)
    model = Counting()
    monkeypatch.setattr(llm, "get_llm", lambda: model)
    pdf, sub = pdfgen.becon_po(pdfgen.NEW_ITEMS, po="231019", per_page=3)
    r = client.post("/api/convert?wait=1", data={"file": (io.BytesIO(pdf), "po-231019.pdf")})
    assert r.status_code == 200 and model.calls == 0
    assert r.headers["X-Dot-Format"] == "BECON" and r.headers["X-Dot-Verified"] == "100.0"
    assert r.headers["X-Dot-Format-Chosen"] == "confident"
    d = fake_db.docs[r.headers["X-Dot-Document"]]
    assert d["read_note"] is None and d["table"]["rows"] == pdfgen.becon_sheet(pdfgen.NEW_ITEMS, "231019", sub)["rows"]


def test_a_file_that_does_not_fit_goes_the_slow_way_and_says_why(client, fake_db, trained, monkeypatch):
    becon_profile(fake_db, trained)
    model = Counting()
    monkeypatch.setattr(llm, "get_llm", lambda: model)
    pdf, _ = pdfgen.becon_po(pdfgen.NEW_ITEMS, header_extra="Discount")
    j = client.post("/api/convert", data={"file": (io.BytesIO(pdf), "po-new-layout.pdf")}).get_json()
    from conftest import wait_for
    f = wait_for(lambda: next((f for f in client.get(f"/api/batches/{j['batch']}").get_json()["files"] if f["stage"] == "converted"), None))
    assert model.calls >= 1
    assert (f["profile_name"], f["read_note"]) == ("BECON", 'header changed: new column "Discount"')


def test_a_direct_read_that_fails_the_checks_goes_the_slow_way(client, fake_db, trained, monkeypatch):
    becon_profile(fake_db, trained)
    model = Counting()
    monkeypatch.setattr(llm, "get_llm", lambda: model)
    real = layout.read_table

    def misread(*a, **k):
        table, note = real(*a, **k)
        table["rows"][0]["Item Code 1"] = "9999999"
        return table, note
    monkeypatch.setattr(layout, "read_table", misread)
    pdf, _ = pdfgen.becon_po(pdfgen.NEW_ITEMS)
    r = client.post("/api/convert?wait=1", data={"file": (io.BytesIO(pdf), "po.pdf")})
    d = fake_db.docs[r.headers["X-Dot-Document"]]
    assert model.calls >= 1 and d["read_note"] == "layout changed: 1 value didn't check out"


def test_a_format_learns_from_its_confirmed_files_the_first_time_it_is_used(fake_db, trained):
    pdf, sheet, _ = trained
    p = fake_db.add_profile("BECON", pdfgen.PO_COLUMNS, pdf)
    info = pdftext.inspect(pdf)
    d = fake_db.create(None, "po-231020.pdf", info)
    d.update(stage="confirmed", confirmed_at=db.now(), profile_id=p["id"], table=sheet)
    fake_db.save(None, d)
    fake_db.pdfs[d["id"]] = pdf
    lay = reading.ensure_layout(None, fake_db.profiles[p["id"]] | {})
    assert lay["variants"] and lay["learned_from"] == [d["id"]]
    assert fake_db.profiles[p["id"]]["layout"]["variants"]


def test_confirming_a_file_teaches_its_layout(fake_db, trained, monkeypatch):
    pdf, sheet, _ = trained
    p = fake_db.add_profile("BECON", pdfgen.PO_COLUMNS, pdf)
    d = fake_db.create(None, "po-231020.pdf", pdftext.inspect(pdf))
    d.update(stage="save_ask", table=sheet, hints=[])
    fake_db.pdfs[d["id"]] = pdf
    saving.confirm(None, d, profile_id=p["id"])
    assert d["stage"] == "confirmed" and fake_db.profiles[p["id"]]["layout"]["variants"]


# ── files with many purchase orders (ECONSAVE-style) ─────────────────────────

def econ(pos):
    pdf, sheet = pdfgen.econsave(pos)
    return pdf, sheet, pdftext.page_texts(pdf)


TEACH = [pdfgen.econ_po("10002-6126036061", "10002 KP", pdfgen.ECON_A), pdfgen.econ_po("10015-6126041889", "10015 KBS", pdfgen.ECON_B)]
BIG = [pdfgen.econ_po("10022-6126044757", "10022 BK", pdfgen.ECON_B + pdfgen.ECON_A),
       pdfgen.econ_po("10067-6126038648", "10067 JM", pdfgen.ECON_A[:2]),
       pdfgen.econ_po("10128-6126042019", "10128 GBK", pdfgen.ECON_A[2:] + pdfgen.ECON_B),
       pdfgen.econ_po("10135-6126000960", "10135 PGH", pdfgen.ECON_A + pdfgen.ECON_B + pdfgen.ECON_A)]


@pytest.fixture(scope="module")
def econ_layout():
    _, sheet, texts = econ(TEACH)
    lay = layout.add(None, sheet, texts, "teach")
    assert "last_problem" not in lay, lay.get("last_problem")
    return lay


def test_a_file_of_many_purchase_orders_is_learned_from_a_small_one(econ_layout):
    v = econ_layout["variants"][0]
    assert v["split_by"] == "PO No." and v["lead_lines"] == 2
    assert [c["col"] for c in v["row"] if c.get("tail")] == ["Description"]


def test_every_purchase_order_of_a_bigger_file_is_read_exactly(econ_layout):
    _, want, texts = econ(BIG)
    table, note = layout.read_table(econ_layout, {"columns": want["columns"]}, texts)
    assert note is None
    assert table["rows"] == want["rows"]


def test_each_purchase_order_keeps_its_own_header_values(econ_layout):
    _, want, texts = econ(BIG)
    table, _ = layout.read_table(econ_layout, {"columns": want["columns"]}, texts)
    per_po = {r["PO No."]: (r["Ship-To Location"], r["Grand Total"]) for r in table["rows"]}
    assert per_po["10067-6126038648"] == ("10067 JM", want["rows"][7]["Grand Total"])
    assert len({r["_doc"] for r in table["rows"]}) == 4


def test_a_number_spilled_after_an_item_stays_with_that_item(econ_layout):
    _, want, texts = econ(BIG)
    table, _ = layout.read_table(econ_layout, {"columns": want["columns"]}, texts)
    assert table["rows"][0]["Description"] == "FC GRIP X7 B/PEN 0.7MM2BL/1BK 3S 547407"
    assert table["rows"][1]["Description"] == "FC GRIP X7 BPEN-R 0.7MM MIX 3S 547408"


def test_the_reference_number_on_each_page_is_never_taken_for_a_spilled_number(econ_layout):
    _, want, texts = econ(BIG)
    table, _ = layout.read_table(econ_layout, {"columns": want["columns"]}, texts)
    assert not any("6126" in r["Description"] for r in table["rows"])


def test_a_format_taught_with_one_purchase_order_says_why_it_cannot_read_many():
    _, sheet, texts = econ(TEACH[:1])
    lay = layout.add(None, sheet, texts, "one")
    _, want, big = econ(BIG)
    assert layout.read_table(lay, {"columns": want["columns"]}, big) == (None, "layout changed: more than one document in the file")


def test_upload_reads_many_purchase_orders_without_the_model(client, fake_db, econ_layout, monkeypatch):
    pdf, want, _ = econ(BIG)
    p = fake_db.add_profile("ECONSAVE", [(c["name"], c["kind"]) for c in want["columns"]], pdf)
    p["layout"] = copy.deepcopy(econ_layout)
    model = Counting()
    monkeypatch.setattr(llm, "get_llm", lambda: model)
    r = client.post("/api/convert?wait=1", data={"file": (io.BytesIO(pdf), "edi_rpt_po_dt1.pdf")})
    assert r.status_code == 200 and model.calls == 0 and r.headers["X-Dot-Format"] == "ECONSAVE"
    assert r.headers["X-Dot-Rows"] == str(len(want["rows"])) and r.headers["X-Dot-Verified"] == "100.0"


def test_a_value_learned_as_followed_by_a_number_is_not_read_where_a_word_follows():
    rule = {"ctx": ["Vendor:"], "after": "#", "n": 2}
    lines = layout_tokens.split_lines(["Vendor: 10586 FABE18 Branch\nVendor: 10586 FABE18 10002 KP"])
    assert layout_tokens.apply_rule(rule, lines) == ["10586 FABE18"]
    assert layout_tokens.apply_rule(rule, lines, where=True)[0][0] == 1


def test_a_purchase_order_the_model_cut_into_pieces_is_learned_as_one():
    _, sheet, texts = econ(TEACH)
    cut = copy.deepcopy(sheet)
    for i, r in enumerate(cut["rows"]):
        r["_doc"] = i
        if i:
            r["Grand Total"] = ""
    lay = layout.add(None, cut, texts, "cut")
    assert "last_problem" not in lay, lay.get("last_problem")
    _, want, big = econ(BIG)
    table, note = layout.read_table(lay, {"columns": want["columns"]}, big)
    assert note is None and table["rows"] == want["rows"]


ADDR = {"10002 KP": ["ECONSAVECASH&CARRY(KP) SDN BHD", "14-22, Jalan Raja Mokhtar 4,", "42200 Kapar, Selangor."],
        "10015 KBS": ["ECONSAVECASH&CARRY(KBS) SDN. BHD.", "Lot 3761, Jalan 2D,", "40150 Shah Alam, Selangor."],
        "10022 BK": ["ECONSAVECASH&CARRY(BK) SDN BHD", "No. 2, PT 45233,", "40460 Shah Alam, Selangor."],
        "10067 JM": ["Econsave Cash&Carry (JM) Sdn Bhd", "No. 1, Jalan Dato Tan,", "45800 Jeram, Selangor."]}


def with_addr(pos):
    return [pdfgen.econ_po(o["po"], o["ship"], o["items"], ADDR[o["ship"]]) for o in pos]


def test_an_address_printed_beside_the_vendor_over_several_lines_is_read():
    _, sheet, texts = econ(with_addr(TEACH))
    lay = layout.add(None, sheet, texts, "addr")
    assert "last_problem" not in lay, lay.get("last_problem")
    assert lay["variants"][0]["fields"]["Address"]["block"] == "Vendor Ship-To Location"
    _, want, big = econ(with_addr(BIG[:2]))
    table, note = layout.read_table(lay, {"columns": want["columns"]}, big)
    assert note is None
    assert {r["Address"] for r in table["rows"]} == {"10022 BK ECONSAVECASH&CARRY(BK) SDN BHD No. 2, PT 45233, 40460 Shah Alam, Selangor.",
                                                     "10067 JM Econsave Cash&Carry (JM) Sdn Bhd No. 1, Jalan Dato Tan, 45800 Jeram, Selangor."}


def test_a_teaching_sheet_with_a_few_model_mistakes_still_teaches_and_the_pdf_wins():
    _, sheet, texts = econ(TEACH + BIG[:1])
    sloppy = copy.deepcopy(sheet)
    rows = sloppy["rows"]
    rows[2]["Item Barcode"] += " 547309"
    rows[2]["Description"] = rows[2]["Description"].replace(" 547309", "")
    rows[0]["Description"] = rows[0]["Description"].replace("R0.5MMBLK", "R 0.5MM BLACK")
    for r in rows:
        if r["_doc"] == 1:
            r["Grand Total"] = ""
    lay = layout.add(None, sloppy, texts, "sloppy")
    assert "last_problem" not in lay, lay.get("last_problem")
    assert lay["variants"][0]["disagree"] >= 1
    table, note = layout.read_table(lay, {"columns": sheet["columns"]}, texts)
    assert note is None and table["rows"] == sheet["rows"]


def test_a_sheet_that_mostly_disagrees_with_the_pdf_teaches_nothing():
    _, sheet, texts = econ(TEACH)
    wrong = copy.deepcopy(sheet)
    for r in wrong["rows"]:
        r["Total Qty."] = "99.00"
    lay = layout.add(None, wrong, texts, "wrong")
    assert not lay["variants"] and lay["last_problem"]


def test_re_read_with_current_format_always_goes_through_the_model(client, fake_db, econ_layout, monkeypatch):
    pdf, want, _ = econ(BIG)
    p = fake_db.add_profile("ECONSAVE", [(c["name"], c["kind"]) for c in want["columns"]], pdf)
    p["layout"] = copy.deepcopy(econ_layout)
    r = client.post("/api/convert?wait=1", data={"file": (io.BytesIO(pdf), "edi_rpt_po_dt1.pdf")})
    did = r.headers["X-Dot-Document"]
    model = Counting()
    monkeypatch.setattr(llm, "get_llm", lambda: model)
    client.post(f"/api/docs/{did}/reread")
    from conftest import wait_for
    wait_for(lambda: client.get(f"/api/docs/{did}").get_json()["doc"]["stage"] != "rereading")
    assert model.calls >= 1
