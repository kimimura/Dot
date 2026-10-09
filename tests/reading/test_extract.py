import re

import pytest

import pdfgen
import config
from modules.reading import extract, parse, prompts, verify
from core import pdftext
from core.ai.errors import LLMError, Truncated

PO = re.compile(r"Purchase\s*Order\s*No\.\s*:\s*(\S+)")
PG = re.compile(r"Page\s*:\s*(\d+)\s*of\s*(\d+)")


class PageReader:
    # answers from the real page text, and can misbehave the way the model did on the ECONSAVE file
    def __init__(self, cap=None, truncate_over=None):
        self.cap, self.truncate_over, self.calls = cap, truncate_over, 0

    def complete(self, pdf, prompt, kind="extract"):
        self.calls += 1
        texts = pdftext.page_texts(pdf)
        if self.truncate_over and len(texts) > self.truncate_over:
            raise Truncated("unreadable result")
        docs, cur, total = [], None, 0
        for t in texts:
            po, (k, _) = PO.search(t).group(1), PG.search(t).groups()
            if cur is None or cur["document_fields"]["Purchase Order No"] != po or k == "1":
                cur = {"document_fields": {"Purchase Order No": po}, "row_columns": ["Barcode", "Description"], "rows": []}
                docs.append(cur)
            for line in t.splitlines():
                m = re.match(r"\s*(\d{13})\s+(.*)", line)
                if m and not (self.cap and total >= self.cap):
                    cur["rows"].append([m.group(1), m.group(2).strip()])
                    total += 1
        return {"signature": {"title": "Purchase Order"}, "documents": docs}


@pytest.fixture(scope="module")
def long_po():
    pdf, truth = pdfgen.purchase_orders(orders=6, pages_per_order=4, items_per_page=12)
    return pdf, truth, pdftext.page_texts(pdf)


@pytest.fixture
def small_chunks(monkeypatch, long_po):
    _, _, texts = long_po
    monkeypatch.setattr(config, "EXTRACT_CHUNK_CHARS", 8 * sum(map(len, texts)) // len(texts))


def got(table):
    return [(r["Purchase Order No"], r["Barcode"]) for r in table["rows"] if r.get("Barcode")]


# ── reading what comes back ──────────────────────────────────────────────────

def test_a_new_format_puts_every_field_in_the_sheet_and_a_saved_one_suggests_extras():
    fmt = {"name": "this document", "columns": [{"name": "Invoice No", "kind": "doc"}], "hints": []}
    fresh, later_part = prompts.build_prompt(), prompts.build_prompt(fmt, fresh=True)
    for p in (fresh, later_part):
        assert "Extract every field printed" in p and "extra_fields" not in p and '"documents": [' in p
    assert "add any other field you find as a new column" in later_part and "Do not add other columns" not in later_part
    saved = prompts.build_prompt({**fmt, "name": "ACME"})
    assert 'put them in "extra_fields"' in saved and '"extra_fields": {}' in saved and "Do not add other columns" in saved


def test_a_new_format_read_in_parts_keeps_fields_found_later(monkeypatch):
    seen = []

    class Reader:
        def complete(self, pdf, prompt, kind="extract"):
            seen.append(prompt)
            fields = {"PO": f"PO-{len(seen)}"} if len(seen) == 1 else {"PO": f"PO-{len(seen)}", "Vendor Tel": "03-1234"}
            return {"documents": [{"document_fields": fields, "row_columns": ["Item"], "rows": [["A"]]}]}
    monkeypatch.setattr(config, "EXTRACT_CHUNK_CHARS", 10)
    pdf = pdfgen.purchase_orders(orders=1, pages_per_order=2)[0]
    table, _, extra = extract.run(Reader(), pdf, texts=pdftext.page_texts(pdf))
    assert "Vendor Tel" in [c["name"] for c in table["columns"]] and extra == {}
    assert all("extra_fields" not in p for p in seen)


def test_rows_given_as_lists_are_matched_to_their_columns():
    parsed = parse.validate({"documents": [{"document_fields": {"Invoice No ": "INV-1"}, "row_columns": ["Item", "Qty"],
                                              "rows": [["A100", 10], ["", ""], {"Item": "A200", "Qty": "5"}]}]})
    d = parsed["documents"][0]
    assert d["document_fields"] == {"Invoice No": "INV-1"}
    assert d["rows"] == [{"Item": "A100", "Qty": "10"}, {"Item": "A200", "Qty": "5"}]


def test_a_flat_reply_without_documents_still_works():
    parsed = parse.validate({"document_fields": {"PO": "1"}, "row_columns": ["Item"], "rows": [["X"]]})
    assert parsed["documents"][0]["rows"] == [{"Item": "X"}]


def test_a_reply_that_is_not_an_object_is_refused():
    with pytest.raises(LLMError):
        parse.validate(["not", "an", "object"])


def test_document_fields_repeat_on_every_row_and_clashing_names_are_kept_apart():
    parsed = parse.validate({"documents": [{"document_fields": {"PO": "1", "Total": "99"}, "row_columns": ["Item", "Total"],
                                              "rows": [["A", "10"], ["B", "89"]]}]})
    t = parse.flatten(parsed)
    assert [c["name"] for c in t["columns"]] == ["PO", "Total", "Item", "Total (Line)"]
    assert [(r["PO"], r["Total"], r["Total (Line)"]) for r in t["rows"]] == [("1", "99", "10"), ("1", "99", "89")]


# ── checking values against the PDF ──────────────────────────────────────────

def test_values_are_checked_against_the_pdf_text():
    t = {"columns": [{"name": "Item", "kind": "row"}, {"name": "Desc", "kind": "row"}],
         "rows": [{"Item": "A100", "Desc": "Blue  Widget"}, {"Item": "Z999", "Desc": ""}]}
    v = verify.verify(t, "A100 Blue Widget 10 50.00", True)
    assert v["cells"] == {"0|Item": "ok", "0|Desc": "ok", "1|Item": "miss", "1|Desc": "na"}
    assert (v["verified"], v["total"], v["checked"]) == (2, 3, True)


def test_typed_values_count_as_edited_not_missing():
    t = {"columns": [{"name": "Item", "kind": "row"}], "rows": [{"Item": "typed by hand"}]}
    assert verify.verify(t, "nothing here", True, edited={"0|Item"})["cells"]["0|Item"] == "edited"


def test_scanned_pdfs_are_not_checked():
    t = {"columns": [{"name": "Item", "kind": "row"}], "rows": [{"Item": "A100"}]}
    v = verify.verify(t, "", False)
    assert v["checked"] is False and v["cells"]["0|Item"] == "na"


# ── long files ───────────────────────────────────────────────────────────────

def test_short_files_are_read_in_one_go():
    assert extract.plan_chunks(["x" * 500] * 8) == [(1, 8)]


def test_long_files_are_cut_by_size_and_scans_by_page_count(monkeypatch):
    monkeypatch.setattr(config, "EXTRACT_CHUNK_CHARS", 1000)
    assert extract.plan_chunks(["x" * 400] * 7) == [(1, 2), (3, 4), (5, 6), (7, 7)]
    assert extract.plan_chunks([""] * 40) == [(1, 15), (16, 30), (31, 40)]


def test_a_document_that_runs_across_two_chunks_is_joined_back_together():
    base = {"columns": [{"name": "PO", "kind": "doc"}, {"name": "Item", "kind": "row"}],
            "rows": [{"_doc": 0, "PO": "P1", "Item": "a"}]}
    more = {"columns": [{"name": "PO", "kind": "doc"}, {"name": "Item", "kind": "row"}, {"name": "UOM", "kind": "row"}],
            "rows": [{"_doc": 0, "PO": "", "Item": "b", "UOM": "PCS"}, {"_doc": 1, "PO": "P2", "Item": "c", "UOM": "BOX"}]}
    extract._append(base, more)
    assert [(r["PO"], r["Item"], r["UOM"]) for r in base["rows"]] == [("P1", "a", ""), ("P1", "b", "PCS"), ("P2", "c", "BOX")]
    a, b, c = (r["_doc"] for r in base["rows"])
    assert a == b != c


def test_a_long_file_comes_back_complete_and_in_order(long_po, small_chunks):
    pdf, truth, texts = long_po
    seen = []
    table, _, _ = extract.run(PageReader(), pdf, texts=texts, progress=lambda done, n: seen.append(done))
    assert got(table) == truth
    assert len({r["_doc"] for r in table["rows"]}) == 6
    assert seen == sorted(seen) and seen[-1] == len(texts)


def test_pages_the_model_skipped_are_read_again(long_po, small_chunks):
    pdf, truth, texts = long_po
    reader = PageReader(cap=50)
    table, _, _ = extract.run(reader, pdf, texts=texts)
    assert got(table) == truth
    assert reader.calls > len(extract.plan_chunks(texts))


def test_a_reply_that_runs_out_of_room_is_split_and_retried(long_po, small_chunks):
    pdf, truth, texts = long_po
    table, _, _ = extract.run(PageReader(truncate_over=4), pdf, texts=texts)
    assert got(table) == truth


def test_every_request_is_said_in_the_terminal(long_po, small_chunks, monkeypatch):
    pdf, truth, texts = long_po
    lines = []
    monkeypatch.setattr(extract.activity, "note", lines.append)
    extract.run(PageReader(truncate_over=4), pdf, texts=texts, name="big.pdf")
    assert lines[0].startswith("big.pdf: request 1, pages 1-") and "answer cut off, asking again in two halves" in lines[0]
    assert all(line.startswith("big.pdf: request ") for line in lines) and len(lines) == len(set(lines))
    assert any(line.endswith(" rows") and "of 24:" in line for line in lines)


def test_a_long_file_that_reads_cleanly_is_never_stopped_however_many_pieces_it_takes(long_po, small_chunks, monkeypatch):
    pdf, truth, texts = long_po
    monkeypatch.setattr(extract.activity, "note", lambda text: None)
    reader = PageReader()
    table, _, _ = extract.run(reader, pdf, texts=texts)
    assert got(table) == truth and reader.calls > 1
