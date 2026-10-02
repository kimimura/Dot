import io
import zipfile

from conftest import wait_for
from helpers import ACME_COLUMNS, csv_rows, upload


def test_one_pdf_in_one_csv_out(client, acme_pdf):
    r = upload(client, acme_pdf)
    assert r.status_code == 200 and r.mimetype == "text/csv"
    rows = csv_rows(r)
    assert rows[0] == ACME_COLUMNS and len(rows) == 3
    assert r.headers["X-Dot-Format-Chosen"] == "new" and r.headers["X-Dot-Rows"] == "2"


def test_the_same_file_twice_reuses_the_first_result(client, acme_pdf):
    upload(client, acme_pdf)
    r = upload(client, acme_pdf, "acme again.pdf")
    assert r.headers["X-Dot-Format-Chosen"] == "reused" and csv_rows(r)[0] == ACME_COLUMNS


def test_a_saved_format_decides_the_columns(client, fake_db, acme_pdf, acme2_pdf):
    fake_db.add_profile("ACME", [("Invoice No", "doc"), ("Item", "row"), ("Qty", "row")], acme_pdf)
    r = upload(client, acme2_pdf)
    assert r.headers["X-Dot-Format"] == "ACME" and r.headers["X-Dot-Format-Chosen"] == "confident"
    assert csv_rows(r) == [["Invoice No", "Item", "Qty"], ["INV-2026-0107", "A300", "3"]]


def test_a_batch_converts_in_the_background_and_zips(client, acme_pdf, orbit_pdf):
    r = client.post("/api/convert", data={"file": [(io.BytesIO(acme_pdf), "acme.pdf"), (io.BytesIO(orbit_pdf), "orbit.pdf"),
                                                   (io.BytesIO(b"hello"), "notes.txt")]})
    j = r.get_json()
    assert len(j["ids"]) == 2 and j["rejected"] == [{"filename": "notes.txt", "error": "Not a PDF."}]
    files = wait_for(lambda: (lambda fs: fs if all(f["stage"] == "converted" for f in fs) else None)(
        client.get(f"/api/batches/{j['batch']}").get_json()["files"]))
    assert all(f["csv_url"] for f in files)
    z = zipfile.ZipFile(io.BytesIO(client.get(f"/api/batches/{j['batch']}/download.zip").data))
    assert sorted(z.namelist()) == ["acme.csv", "orbit.csv"]


def test_a_broken_pdf_gets_a_plain_message(client):
    r = upload(client, b"%PDF-1.4 this is not really a pdf", "broken.pdf")
    say = r.get_json()["say"]
    assert r.status_code == 400 and say.startswith("PDF can't be opened")
