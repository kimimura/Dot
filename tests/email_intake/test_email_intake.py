import base64
import csv
import io
import time

import pytest

import config
from conftest import wait_for
from core import activity, webhook
from core.ai.errors import LLMError
from modules.conversion import convert
from modules.email_intake import message, service

TOKEN = "test-token"


@pytest.fixture
def sent(monkeypatch, fake_db):
    monkeypatch.setattr(config, "EMAIL_INTAKE_TOKEN", TOKEN)
    monkeypatch.setattr(config, "EMAIL_ALERT_URL", "https://alerts.example/flow")
    monkeypatch.setattr(config, "EMAIL_POLL_SECONDS", 0.02)
    monkeypatch.setattr(config, "EMAIL_ALERT_RETRY_SECONDS", 0)
    out = []
    monkeypatch.setattr(webhook, "post_json", lambda url, payload, timeout: out.append(payload) or 202)
    return out


def b64(data):
    return base64.b64encode(data).decode()


def send(client, files, token=TOKEN):
    return client.post("/api/email/intake", json={"type": "Dot", "email": "sender@example.com", "files": files}, headers={"Token": token})


def only_email(fake_db):
    return next(s for s in fake_db.submissions.values() if s["source"] == "email")


def sheet_rows(attachment):
    return list(csv.reader(io.StringIO(attachment["ContentBytes"])))


def test_pdfs_from_an_email_come_back_as_sheets_named_by_format(client, fake_db, sent, acme_pdf, acme2_pdf, orbit_pdf):
    fake_db.add_profile("ACME", [("Invoice No", "doc"), ("Item", "row"), ("Qty", "row")], acme_pdf)
    r = send(client, [{"filename": "a.pdf", "content": b64(acme_pdf)}, {"name": "b.PDF", "contentBytes": b64(acme2_pdf)},
                      {"filename": "c.pdf", "content": b64(orbit_pdf)}, {"filename": "logo.png", "content": b64(b"\x89PNG")}])
    assert r.status_code == 200 and r.get_json() == {"status": "accepted", "count": 3, "files": ["a.pdf", "b.PDF", "c.pdf"],
                                                     "skipped": [{"file": "logo.png", "reason": "Not a PDF."}]}
    payload, stamp = wait_for(lambda: sent and sent[0]), only_email(fake_db)["stamp"]
    assert payload["subject"] == "3 PDFs Received" and payload["to"] == "sender@example.com"
    assert [a["Name"] for a in payload["attachments"]] == [f"ACME_SalesOrder_{stamp}_1.csv", f"ACME_SalesOrder_{stamp}_2.csv",
                                                            f"Unidentified_SalesOrder_{stamp}.csv"]
    assert "a.pdf – ACME" in payload["body"] and "c.pdf – Unidentified" in payload["body"]
    assert sheet_rows(payload["attachments"][1]) == [["Invoice No", "Item", "Qty", "Received From"],
                                                     ["INV-2026-0107", "A300", "3", "sender@example.com"]]
    assert only_email(fake_db)["status"] == "sent" and len(sent) == 1


def test_an_email_preview_with_raw_line_breaks_is_still_read(client, fake_db, sent, acme_pdf):
    raw = '{"type": "Dot\r\nRegards,\r\nBrian", "email": "sender@example.com", "files": [{"filename": "a.pdf", "content": "%s"}]}' % b64(acme_pdf)
    r = client.post("/api/email/intake", data=raw, headers={"Token": TOKEN, "Content-Type": "application/json"})
    assert r.status_code == 200 and r.get_json()["count"] == 1
    assert wait_for(lambda: sent and sent[0])["subject"] == "1 PDF Received"


def test_files_are_listed_in_the_order_the_email_carried_them(client, fake_db, sent, acme_pdf, acme2_pdf):
    send(client, [{"filename": "z.pdf", "content": b64(acme_pdf)}, {"filename": "a.pdf", "content": b64(acme2_pdf)}])
    body = wait_for(lambda: sent and sent[0])["body"]
    assert body.index("z.pdf") < body.index("a.pdf")


@pytest.mark.parametrize("token, configured", [("wrong", TOKEN), (TOKEN, "")])
def test_without_the_right_token_nothing_is_taken_in(client, fake_db, sent, monkeypatch, acme_pdf, token, configured):
    monkeypatch.setattr(config, "EMAIL_INTAKE_TOKEN", configured)
    r = send(client, [{"filename": "a.pdf", "content": b64(acme_pdf)}], token=token)
    assert r.status_code == 403 and not fake_db.docs and not fake_db.submissions


def test_an_email_without_a_readable_pdf_is_turned_away(client, fake_db, sent):
    r = send(client, [{"filename": "logo.png", "content": b64(b"png")}, {"filename": "x.pdf", "content": b64(b"not a pdf")}])
    assert r.status_code == 415 and r.get_json()["status"] == "rejected" and len(r.get_json()["skipped"]) == 2
    assert only_email(fake_db)["status"] == "rejected" and not fake_db.docs and not sent
    assert send(client, []).status_code == 400


def test_a_pdf_that_fails_is_listed_without_a_sheet(client, fake_db, sent, monkeypatch, acme_pdf):
    def unavailable(conn, llm, d, pdf):
        raise LLMError("the reader is unavailable")
    monkeypatch.setattr(convert, "convert", unavailable)
    send(client, [{"filename": "a.pdf", "content": b64(acme_pdf)}])
    payload = wait_for(lambda: sent and sent[0])
    assert payload["subject"] == "1 PDF Received" and payload["attachments"] == [] and payload["failed_count"] == 1
    assert "a.pdf – Could not be read" in payload["body"]


def test_results_that_cannot_be_sent_are_tried_again_then_marked_failed(client, fake_db, sent, monkeypatch, acme_pdf):
    tries = []

    def down(url, payload, timeout):
        tries.append(url)
        raise webhook.WebhookError("the alert address answered 502")
    monkeypatch.setattr(webhook, "post_json", down)
    send(client, [{"filename": "a.pdf", "content": b64(acme_pdf)}])
    done = wait_for(lambda: only_email(fake_db)["status"] != "waiting" and only_email(fake_db))
    assert done["status"] == "failed" and "502" in done["error"] and len(tries) == config.EMAIL_ALERT_TRIES


def test_results_still_go_out_after_a_restart(client, fake_db, sent, monkeypatch, acme_pdf):
    watch = service._watch
    monkeypatch.setattr(service, "_watch", lambda rid: None)
    send(client, [{"filename": "a.pdf", "content": b64(acme_pdf)}])
    wait_for(lambda: all(d["stage"] == "converted" for d in fake_db.docs.values()))
    assert not sent and only_email(fake_db)["status"] == "waiting"
    monkeypatch.setattr(service, "_watch", watch)
    monkeypatch.setattr(config, "EMAIL_INTAKE_TOKEN", "")
    service.resume()
    time.sleep(0.3)
    assert not sent and only_email(fake_db)["status"] == "waiting"
    monkeypatch.setattr(config, "EMAIL_INTAKE_TOKEN", TOKEN)
    service.resume()
    wait_for(lambda: only_email(fake_db)["status"] == "sent")
    assert [p["subject"] for p in sent] == ["1 PDF Received"]


def test_the_message_uses_safe_file_names_and_plain_wording():
    table = {"columns": [{"name": "A", "kind": "row"}], "rows": [{"A": "1"}]}
    docs = [{"filename": "<x>.pdf", "stage": "converted", "profile_name": "PO/ACME", "table": table},
            {"filename": "y.pdf", "stage": "converting", "profile_name": None, "table": None}]
    p = message.build(docs, "20261223_140031", "s@example.com")
    assert p["subject"] == "2 PDFs Received" and [a["Name"] for a in p["attachments"]] == ["PO-ACME_SalesOrder_20261223_140031.csv"]
    assert "&lt;x&gt;.pdf – PO/ACME</b><br>1 line · PO-ACME_SalesOrder_20261223_140031.csv" in p["body"]
    assert "y.pdf – Still processing</b></p>" in p["body"]


def test_the_terminal_shows_what_happens_to_an_email(client, fake_db, sent, monkeypatch, acme_pdf, acme2_pdf, orbit_pdf):
    lines = []
    monkeypatch.setattr(activity, "note", lines.append)
    fake_db.add_profile("ACME", [("Invoice No", "doc"), ("Item", "row"), ("Qty", "row")], acme_pdf)
    send(client, [{"filename": "a.pdf", "content": b64(acme2_pdf)}, {"filename": "c.pdf", "content": b64(orbit_pdf)}])
    wait_for(lambda: any(line.startswith("Reply sent") for line in lines))
    assert lines[0] == "Email from sender@example.com: 2 PDFs"
    assert "Reading a.pdf" in lines and "Reading c.pdf" in lines
    assert any(line.startswith("Done: a.pdf: ACME, read by the model, 1 row, ") for line in lines)
    assert any(line.startswith("Done: c.pdf: unknown format, read by the model, ") for line in lines)
    assert lines[-1] == 'Reply sent to sender@example.com: "2 PDFs Received"'
