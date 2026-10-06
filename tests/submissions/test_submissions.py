import base64
import io

import config
from conftest import wait_for
from core.ai.errors import LLMError
from helpers import upload
from modules.conversion import convert


def batch(client, files, batch_id=None):
    url = "/api/convert" + (f"?batch={batch_id}" if batch_id else "")
    return client.post(url, data={"file": [(io.BytesIO(pdf), name) for name, pdf in files]}).get_json()


def test_every_way_in_is_recorded_with_where_it_came_from(client, fake_db, acme_pdf, acme2_pdf):
    upload(client, acme_pdf)
    client.post("/api/upload", data={"file": (io.BytesIO(acme2_pdf), "dropped.pdf")})
    assert sorted(s["source"] for s in fake_db.submissions.values()) == ["builder", "upload"]
    assert all(d["submission_id"] in fake_db.submissions for d in fake_db.docs.values())


def test_the_library_shows_where_each_file_came_in(client, fake_db, monkeypatch, acme_pdf, acme2_pdf, orbit_pdf):
    monkeypatch.setattr(config, "EMAIL_INTAKE_TOKEN", "t")
    upload(client, acme_pdf, "uploaded.pdf")
    client.post("/api/upload", data={"file": (io.BytesIO(acme2_pdf), "dropped.pdf")})
    client.post("/api/email/intake", headers={"Token": "t"},
                json={"email": "s@example.com", "files": [{"filename": "emailed.pdf", "content": base64.b64encode(orbit_pdf).decode()}]})
    listed = {d["filename"]: (d["source"], d["sender"]) for d in client.get("/api/docs").get_json()["docs"]}
    assert listed == {"uploaded.pdf": ("upload", ""), "dropped.pdf": ("builder", ""), "emailed.pdf": ("email", "s@example.com")}
    emailed = next(d["id"] for d in fake_db.docs.values() if d["filename"] == "emailed.pdf")
    assert client.get(f"/api/docs/{emailed}").get_json()["doc"]["source"] == "email"


def test_files_added_to_a_batch_keep_coming_after_the_earlier_ones(client, fake_db, acme_pdf, acme2_pdf, orbit_pdf):
    first = batch(client, [("z.pdf", acme_pdf)])
    batch(client, [("b.pdf", acme2_pdf), ("a.pdf", orbit_pdf)], first["batch"])
    files = client.get(f"/api/batches/{first['batch']}").get_json()["files"]
    assert [f["filename"] for f in files] == ["z.pdf", "b.pdf", "a.pdf"]
    assert len([s for s in fake_db.submissions.values() if s["source"] == "upload"]) == 1


def test_only_files_converted_in_bulk_can_be_retried_or_removed_there(client, fake_db, monkeypatch, acme_pdf, acme2_pdf):
    def unavailable(conn, llm, d, pdf):
        raise LLMError("the reader is unavailable")
    monkeypatch.setattr(convert, "convert", unavailable)
    bulk = batch(client, [("a.pdf", acme_pdf)])["ids"][0]
    wait_for(lambda: fake_db.docs[bulk]["stage"] == "failed")
    dropped = client.post("/api/upload", data={"file": (io.BytesIO(acme2_pdf), "b.pdf")}).get_json()["doc"]["id"]
    fake_db.docs[dropped]["stage"] = "failed"
    assert client.post(f"/api/docs/{dropped}/reconvert").status_code == 400
    assert client.post(f"/api/docs/{dropped}/cancel").status_code == 409 and dropped in fake_db.docs
    assert client.post(f"/api/docs/{bulk}/cancel").status_code == 200 and bulk not in fake_db.docs
