import csv
import io
import time

from core import db, jobs
from modules.conversion import intake, queue
from modules.documents import repository as documents
from modules.submissions import repository as submissions

ACME_COLUMNS = ["Invoice No", "Date", "Customer", "Total", "Item", "Description", "Qty", "Price"]


def convert(pdf, name="acme.pdf", sender=""):
    # a PDF arriving the way an email brings one, read straight away by what its format has learned
    conn = db.connect()
    sid = db.new_id()
    submissions.create(conn, sid, "email", sender=sender)
    ids, rejected = intake.store(conn, [(name, pdf)], sid)
    assert ids, rejected
    queue.run(ids[0])
    return documents.get(conn, ids[0])


def read_in_builder(client, pdf, name="acme.pdf"):
    # a PDF dropped in Profile Builder and read; a format it recognises is accepted when asked
    did = client.post("/api/upload", data={"file": (io.BytesIO(pdf), name)}, content_type="multipart/form-data").get_json()["doc"]["id"]
    settle(did)
    if documents.get(db.connect(), did)["stage"] == "identify":
        client.post(f"/api/docs/{did}/answer", json={"option": "yes"})
        settle(did)
    return did


def save_as(client, did, name):
    # from review: "yes, that's the format", "yes, save it", then the format's name
    for option, extra in (("yes", {}), ("yes", {}), ("submit", {"name": name})):
        env = client.post(f"/api/docs/{did}/answer", json={"option": option, **extra}).get_json()
    return env


def teach(client, pdf, fmt, name="acme.pdf"):
    did = read_in_builder(client, pdf, name)
    save_as(client, did, fmt)
    return did


def settle(did):
    # a file being read in the background is done once its reading job lets go of it
    end = time.time() + 30
    while (jobs.running(did) or jobs.queued(did) or (documents.get(db.connect(), did) or {}).get("stage") == "extracting") and time.time() < end:
        time.sleep(0.01)


def format_name(fake_db, d):
    return (fake_db.profiles.get(d.get("profile_id")) or {}).get("name")


def csv_rows(resp):
    return list(csv.reader(io.StringIO(resp.data.decode("utf-8-sig"))))


def columns(env):
    return [c["name"] for c in env["table"]["columns"]]


def teach_acme(client, pdf):
    # the ACME format as most tests want it: invoice number, item, quantity and price, the rest dropped in Profile Builder
    did = read_in_builder(client, pdf)
    client.post(f"/api/docs/{did}/ops", json={"ops": [{"op": "drop_col", "col": c} for c in ("Date", "Customer", "Total", "Description")]})
    save_as(client, did, "ACME")
    return did


def keep_in_library(client, pdf, name):
    # a file read in Profile Builder and kept without saving a format: it stays unidentified
    did = read_in_builder(client, pdf, name)
    for option in ("yes", "no"):
        client.post(f"/api/docs/{did}/answer", json={"option": option})
    return did
