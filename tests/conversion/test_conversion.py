from core import db
from helpers import ACME_COLUMNS, convert, format_name
from modules.conversion import intake


def test_a_new_format_is_read_in_full(fake_db, acme_pdf):
    d = convert(acme_pdf)
    assert d["stage"] == "converted" and d["auto_how"] == "new"
    assert [c["name"] for c in d["table"]["columns"]] == ACME_COLUMNS and len(d["table"]["rows"]) == 2


def test_the_same_file_twice_reuses_the_first_result(fake_db, acme_pdf):
    first = convert(acme_pdf)
    again = convert(acme_pdf, "acme again.pdf")
    assert again["auto_how"] == "reused" and again["table"]["rows"] == first["table"]["rows"]


def test_a_saved_format_decides_the_columns(fake_db, acme_pdf, acme2_pdf):
    fake_db.add_profile("ACME", [("Invoice No", "doc"), ("Item", "row"), ("Qty", "row")], acme_pdf)
    d = convert(acme2_pdf)
    assert format_name(fake_db, d) == "ACME" and d["auto_how"] == "confident"
    assert [c["name"] for c in d["table"]["columns"]] == ["Invoice No", "Item", "Qty"]
    assert [{k: v for k, v in r.items() if not k.startswith("_")} for r in d["table"]["rows"]] == [
        {"Invoice No": "INV-2026-0107", "Item": "A300", "Qty": "3"}]


def test_a_broken_pdf_is_turned_away_with_a_plain_reason(fake_db):
    fake_db.add_submission(None, "s1", "email")
    ids, rejected = intake.store(db.connect(), [("broken.pdf", b"%PDF-1.4 this is not really a pdf"), ("notes.txt", b"hi")], "s1")
    assert ids == [] and rejected[0]["error"].startswith("PDF can't be opened")
    assert rejected[1] == {"filename": "notes.txt", "error": "Not a PDF."}
