import base64
import io

import pytest

import config
from conftest import wait_for
from core import webhook
from helpers import convert


@pytest.fixture(autouse=True)
def quick_replies(monkeypatch):
    monkeypatch.setattr(config, "EMAIL_INTAKE_TOKEN", "t")
    monkeypatch.setattr(config, "EMAIL_ALERT_URL", "https://alerts.example/flow")
    monkeypatch.setattr(config, "EMAIL_POLL_SECONDS", 0.02)
    monkeypatch.setattr(webhook, "post_json", lambda url, payload, timeout: 202)


def email(client, files):
    return client.post("/api/email/intake", headers={"Token": "t"},
                       json={"email": "s@example.com", "files": [{"filename": n, "content": base64.b64encode(p).decode()} for n, p in files]})


def test_every_way_in_is_recorded_with_where_it_came_from(client, fake_db, acme_pdf, acme2_pdf):
    convert(acme_pdf)
    client.post("/api/upload", data={"file": (io.BytesIO(acme2_pdf), "dropped.pdf")})
    assert sorted(s["source"] for s in fake_db.submissions.values()) == ["builder", "email"]
    assert all(d["submission_id"] in fake_db.submissions for d in fake_db.docs.values())


def test_the_library_shows_where_each_file_came_in(client, fake_db, acme2_pdf, orbit_pdf):
    client.post("/api/upload", data={"file": (io.BytesIO(acme2_pdf), "dropped.pdf")})
    email(client, [("emailed.pdf", orbit_pdf)])
    listed = {d["filename"]: (d["source"], d["sender"]) for d in client.get("/api/docs").get_json()["docs"]}
    assert listed == {"dropped.pdf": ("builder", ""), "emailed.pdf": ("email", "s@example.com")}
    emailed = next(d["id"] for d in fake_db.docs.values() if d["filename"] == "emailed.pdf")
    assert client.get(f"/api/docs/{emailed}").get_json()["doc"]["source"] == "email"


def test_the_files_of_an_email_keep_the_order_they_were_attached_in(client, fake_db, acme_pdf, acme2_pdf, orbit_pdf):
    email(client, [("z.pdf", acme_pdf), ("b.pdf", acme2_pdf), ("a.pdf", orbit_pdf)])
    sid = next(s for s in fake_db.submissions if fake_db.submissions[s]["source"] == "email")
    wait_for(lambda: fake_db.submissions[sid]["status"] == "sent")
    assert [f["filename"] for f in fake_db.list_submission(None, sid)] == ["z.pdf", "b.pdf", "a.pdf"]
