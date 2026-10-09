from core import activity, db, pdftext
from core.ai.offline import OfflineAdapter
from helpers import ACME_COLUMNS, convert, format_name, teach
from modules.conversion import intake, reading
from modules.reading import layout


def test_an_emailed_file_of_a_taught_format_is_read_by_its_layout_with_no_model(client, fake_db, acme_pdf, acme2_pdf, monkeypatch):
    teach(client, acme_pdf, "ACME")
    asked = []
    monkeypatch.setattr(OfflineAdapter, "complete", lambda self, *a, **k: asked.append(a))
    d = convert(acme2_pdf)
    assert format_name(fake_db, d) == "ACME" and d["auto_how"] == "confident" and asked == []
    assert [c["name"] for c in d["table"]["columns"]] == ACME_COLUMNS
    assert [(r["Invoice No"], r["Item"], r["Qty"]) for r in d["table"]["rows"]] == [("INV-2026-0107", "A300", "3")]


def test_an_emailed_file_of_an_unknown_format_is_not_read_and_says_where_to_teach_it(fake_db, acme_pdf, monkeypatch):
    asked = []
    monkeypatch.setattr(OfflineAdapter, "complete", lambda self, *a, **k: asked.append(a))
    d = convert(acme_pdf)
    assert d["stage"] == "failed" and d["error"] == "unknown format; open it in Profile Builder" and not d["table"] and asked == []


def test_an_emailed_file_that_doesnt_fit_its_layout_is_not_guessed(client, fake_db, acme_pdf, acme2_pdf, monkeypatch):
    teach(client, acme_pdf, "ACME")
    monkeypatch.setattr(reading, "read_direct", lambda conn, d, prof, texts: (None, None, 'layout changed: "Qty" not found in 1 row'))
    d = convert(acme2_pdf)
    assert d["stage"] == "failed" and d["error"] == 'ACME, layout changed: "Qty" not found in 1 row; open it in Profile Builder'


def test_the_same_file_twice_reuses_the_first_result(client, fake_db, acme_pdf):
    taught = teach(client, acme_pdf, "ACME")
    again = convert(acme_pdf, "acme again.pdf")
    assert again["auto_how"] == "reused" and again["table"]["rows"] == fake_db.docs[taught]["table"]["rows"]


def test_a_broken_pdf_is_turned_away_with_a_plain_reason(fake_db):
    fake_db.add_submission(None, "s1", "email")
    ids, rejected = intake.store(db.connect(), [("broken.pdf", b"%PDF-1.4 this is not really a pdf"), ("notes.txt", b"hi")], "s1")
    assert ids == [] and rejected[0]["error"].startswith("PDF can't be opened")
    assert rejected[1] == {"filename": "notes.txt", "error": "Not a PDF."}


def twin(fake_db, name, pdf, keep, taught_at):
    # a format taught from the same PDF as another, keeping its own columns
    full = ["Invoice No", "Date", "Customer", "Total", "Item", "Description", "Qty", "Price"]
    rows = [("INV-2026-0091", "12/09/2026", "Beta Retail", "1,250.00", "A100", "Blue Widget", "10", "50.00"),
            ("INV-2026-0091", "12/09/2026", "Beta Retail", "1,250.00", "A200", "Red Widget", "5", "150.00")]
    kinds = {c: "doc" if c in ("Invoice No", "Date", "Customer", "Total") else "row" for c in full}
    p = fake_db.add_profile(name, [(c, kinds[c]) for c in keep], pdf)
    sheet = {"columns": [{"name": c, "kind": kinds[c]} for c in keep], "rows": [{"_doc": 0, **{c: v for c, v in zip(full, r) if c in keep}} for r in rows]}
    p.update(layout=layout.add(None, sheet, pdftext.page_texts(pdf), "taught"), updated_at=taught_at)
    return p


def test_two_formats_taught_from_the_same_pdf_go_to_the_one_taught_last(fake_db, acme_pdf, acme2_pdf, monkeypatch):
    twin(fake_db, "ECONSAVE", acme_pdf, ["Invoice No", "Item", "Qty", "Price"], "2026-10-08T10:00:00")
    twin(fake_db, "ECONSAVE2", acme_pdf, ["Invoice No", "Customer", "Item", "Description", "Qty", "Price"], "2026-10-08T11:00:00")
    lines = []
    monkeypatch.setattr(activity, "note", lines.append)
    d = convert(acme2_pdf, "emailed.pdf")
    assert format_name(fake_db, d) == "ECONSAVE2" and [c["name"] for c in d["table"]["columns"]][1] == "Customer"
    assert any(x.startswith("emailed.pdf: fits ") and x.endswith("; using ECONSAVE2, the one taught last") for x in lines)


def test_of_two_formats_that_look_alike_the_one_whose_layout_fits_is_used(fake_db, acme_pdf, acme2_pdf):
    twin(fake_db, "ACME", acme_pdf, ["Invoice No", "Item", "Qty", "Price"], "2026-10-08T10:00:00")
    fake_db.add_profile("ACME OLD", [("Invoice No", "doc")], acme_pdf)["updated_at"] = "2026-10-08T12:00:00"
    d = convert(acme2_pdf)
    assert format_name(fake_db, d) == "ACME" and d["stage"] == "converted"


def test_editing_a_format_on_the_profiles_page_makes_it_the_one_edited_last(client, fake_db, acme_pdf, acme2_pdf):
    first = twin(fake_db, "ECONSAVE", acme_pdf, ["Invoice No", "Item", "Qty", "Price"], "2026-10-08T10:00:00")
    twin(fake_db, "ECONSAVE2", acme_pdf, ["Invoice No", "Customer", "Item", "Description", "Qty", "Price"], "2026-10-08T11:00:00")
    assert client.put(f"/api/profiles/{first['id']}", json={"hints": [{"text": "Use the delivery date"}]}).status_code == 200
    assert format_name(fake_db, convert(acme2_pdf)) == "ECONSAVE"
