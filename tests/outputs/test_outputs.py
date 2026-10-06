import base64

import pytest

import config
from conftest import wait_for
from core import webhook
from helpers import upload
from modules.outputs import build

COLUMNS = [{"name": "PO No.", "kind": "doc", "field": "order_number"}, {"name": "Date", "kind": "doc", "field": "order_date"},
           {"name": "Printed on", "kind": "doc"}, {"name": "Grand Total", "kind": "doc", "field": "grand_total"},
           {"name": "Item", "kind": "row", "field": "item_code"}, {"name": "Unit Price (RM)", "kind": "row", "field": "unit_price"},
           {"name": "Free Unit", "kind": "row"}]


def row(doc, po, item, price, free=""):
    return {"_doc": doc, "PO No.": po, "Date": "30/09/2026", "Printed on": "01/10/2026 09:05:57", "Grand Total": "8,395.49",
            "Item": item, "Unit Price (RM)": price, "Free Unit": free}


def test_a_file_with_several_orders_becomes_one_entry_per_order_with_its_own_rows():
    table = {"columns": COLUMNS, "rows": [row(0, "10018-1", "519140009", "9.9100", "0.00"), row(0, "10018-1", "519110014", "9.5100"),
                                          row(1, "10022-2", "543000087", "3.0600", "0.00")]}
    out = build.build(table, "ECONSAVE", "dmy", "2026-10-06 10:15:42")
    assert out == {"chain": "ECONSAVE", "process_date": "2026-10-06 10:15:42", "orders": [
        {"order_number": "10018-1", "order_date": "2026-09-30", "printed_on": "2026-10-01 09:05:57", "grand_total": "8,395.49",
         "rows": [{"item_code": "519140009", "unit_price": "9.9100", "free_unit": "0.00"},
                  {"item_code": "519110014", "unit_price": "9.5100", "free_unit": ""}]},
        {"order_number": "10022-2", "order_date": "2026-09-30", "printed_on": "2026-10-01 09:05:57", "grand_total": "8,395.49",
         "rows": [{"item_code": "543000087", "unit_price": "3.0600", "free_unit": "0.00"}]}]}


@pytest.mark.parametrize("printed, order, want", [("01/02/2026", "dmy", "2026-02-01"), ("01/02/2026", "mdy", "2026-01-02"),
                                                  ("2026-02-01", "ymd", "2026-02-01"), ("30.09.26", "dmy", "2026-09-30"),
                                                  ("20/10/2026 18:00", "dmy", "2026-10-20 18:00:00"), ("13/13/2026", "dmy", "13/13/2026"),
                                                  ("FC PEN 0.5/1.0/2", "dmy", "FC PEN 0.5/1.0/2"), ("8,395.49", "dmy", "8,395.49")])
def test_only_whole_dates_change_and_only_into_one_style(printed, order, want):
    assert build.standard_date(printed, order) == want


def test_a_converted_file_of_a_known_format_keeps_its_output_and_an_unknown_one_none(client, fake_db, acme_pdf, acme2_pdf, orbit_pdf):
    fake_db.add_profile("ACME", [("Invoice No", "doc"), ("Item", "row"), ("Qty", "row")], acme_pdf)
    known = upload(client, acme2_pdf).headers["X-Dot-Document"]
    unknown = upload(client, orbit_pdf, "orbit.pdf").headers["X-Dot-Document"]
    out = fake_db.outputs[(known, "current")]
    assert out["chain"] == "ACME" and out["orders"][0]["invoice_no"] == "INV-2026-0107"
    assert out["orders"][0]["rows"] == [{"item": "A300", "qty": "3"}]
    assert (unknown, "current") not in fake_db.outputs


def test_an_edit_updates_the_current_output(client, fake_db, acme_pdf, acme2_pdf):
    fake_db.add_profile("ACME", [("Invoice No", "doc"), ("Item", "row"), ("Qty", "row")], acme_pdf)
    did = upload(client, acme2_pdf).headers["X-Dot-Document"]
    client.post(f"/api/docs/{did}/ops", json={"ops": [{"op": "set_cell", "row": 0, "col": "Qty", "value": "7"}]})
    assert fake_db.outputs[(did, "current")]["orders"][0]["rows"][0]["qty"] == "7"


def test_what_was_sent_is_kept_as_it_was(client, fake_db, monkeypatch, acme_pdf, acme2_pdf):
    fake_db.add_profile("ACME", [("Invoice No", "doc"), ("Item", "row"), ("Qty", "row")], acme_pdf)
    monkeypatch.setattr(config, "EMAIL_INTAKE_TOKEN", "t")
    monkeypatch.setattr(config, "EMAIL_ALERT_URL", "https://alerts.example/flow")
    monkeypatch.setattr(config, "EMAIL_POLL_SECONDS", 0.02)
    sent = []
    monkeypatch.setattr(webhook, "post_json", lambda url, payload, timeout: sent.append(payload) or 202)
    r = client.post("/api/email/intake", headers={"Token": "t"},
                    json={"email": "s@example.com", "files": [{"filename": "a.pdf", "content": base64.b64encode(acme2_pdf).decode()}]})
    assert r.status_code == 200
    did = wait_for(lambda: next((k[0] for k in fake_db.outputs if k[1] == "sent"), None))
    client.post(f"/api/docs/{did}/ops", json={"ops": [{"op": "set_cell", "row": 0, "col": "Qty", "value": "7"}]})
    assert fake_db.outputs[(did, "sent")]["orders"][0]["rows"][0]["qty"] == "3"
    assert fake_db.outputs[(did, "current")]["orders"][0]["rows"][0]["qty"] == "7"
