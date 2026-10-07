import json

from helpers import convert, csv_rows


def known_and_unknown(client, fake_db, acme_pdf, acme2_pdf, orbit_pdf):
    fake_db.add_profile("ACME", [("Invoice No", "doc"), ("Item", "row"), ("Qty", "row")], acme_pdf)
    known = convert(acme2_pdf, sender="orders@chain.example")["id"]
    unknown = convert(orbit_pdf, "orbit.pdf")["id"]
    return known, unknown


def test_a_known_format_downloads_its_sheet_as_csv_and_its_output_as_json(client, fake_db, acme_pdf, acme2_pdf, orbit_pdf):
    known, _ = known_and_unknown(client, fake_db, acme_pdf, acme2_pdf, orbit_pdf)
    doc = client.get(f"/api/docs/{known}").get_json()["doc"]
    assert doc["has_output"] and doc["csv_url"].endswith("/download.csv") and doc["json_url"].endswith("/download.json")
    data = json.loads(client.get(doc["json_url"]).data)
    assert data == fake_db.outputs[(known, "current")] and data["received_from"] == "orders@chain.example"
    assert csv_rows(client.get(doc["csv_url"])) == [["Invoice No", "Item", "Qty", "Received From"],
                                                    ["INV-2026-0107", "A300", "3", "orders@chain.example"]]


def test_a_file_read_before_outputs_were_kept_still_has_its_json(client, fake_db, acme_pdf, acme2_pdf, orbit_pdf):
    known, _ = known_and_unknown(client, fake_db, acme_pdf, acme2_pdf, orbit_pdf)
    fake_db.outputs.clear()
    r = client.get(f"/api/docs/{known}/download.json")
    assert r.status_code == 200 and json.loads(r.data)["orders"][0]["invoice_no"] == "INV-2026-0107"


def test_an_unidentified_file_gets_csv_json_and_pdf_too(client, fake_db, acme_pdf, acme2_pdf, orbit_pdf):
    _, unknown = known_and_unknown(client, fake_db, acme_pdf, acme2_pdf, orbit_pdf)
    doc = client.get(f"/api/docs/{unknown}").get_json()["doc"]
    assert doc["has_output"] and doc["json_url"].endswith("/download.json")
    assert json.loads(client.get(doc["json_url"]).data)["chain"] == "Unidentified"
    assert csv_rows(client.get(doc["csv_url"]))[0] == [c["name"] for c in fake_db.docs[unknown]["table"]["columns"]] + ["Received From"]
    pdf = client.get(doc["pdf_url"])
    assert pdf.data == orbit_pdf and pdf.headers["Content-Disposition"].startswith("attachment; filename=orbit.pdf")


def test_excel_is_no_longer_offered(client, fake_db, acme_pdf, acme2_pdf, orbit_pdf):
    known, _ = known_and_unknown(client, fake_db, acme_pdf, acme2_pdf, orbit_pdf)
    assert "xlsx_url" not in client.get(f"/api/docs/{known}").get_json()["doc"]
    assert client.get(f"/api/docs/{known}/download.xlsx").status_code == 404


def test_a_file_its_format_learns_from_is_marked_with_how_many_others_teach_it(client, fake_db, acme_pdf, acme2_pdf, orbit_pdf):
    known, unknown = known_and_unknown(client, fake_db, acme_pdf, acme2_pdf, orbit_pdf)

    def marks(did):
        doc = client.get(f"/api/docs/{did}").get_json()["doc"]
        row = next(r for r in client.get("/api/docs").get_json()["docs"] if r["id"] == did)
        assert (row["teaches"], row["teachers"]) == (doc["teaches"], doc["teachers"])
        return doc["teaches"], doc["teachers"]

    assert marks(known) == (False, 0) and marks(unknown) == (False, 0)
    fake_db.docs[known]["stage"] = "confirmed"
    assert marks(known) == (True, 1)
    again = convert(acme2_pdf, "acme_copy.pdf")["id"]
    fake_db.docs[again]["stage"] = "confirmed"
    assert marks(known) == (True, 2) and marks(again) == (True, 2)
