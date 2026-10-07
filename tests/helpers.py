import csv
import io

from core import db
from modules.conversion import intake, queue
from modules.documents import repository as documents
from modules.submissions import repository as submissions

ACME_COLUMNS = ["Invoice No", "Date", "Customer", "Total", "Item", "Description", "Qty", "Price"]


def convert(pdf, name="acme.pdf", sender=""):
    # a PDF arriving the way an email brings one, converted straight away instead of waiting in the queue
    conn = db.connect()
    sid = db.new_id()
    submissions.create(conn, sid, "email", sender=sender)
    ids, rejected = intake.store(conn, [(name, pdf)], sid)
    assert ids, rejected
    queue.run(ids[0])
    return documents.get(conn, ids[0])


def format_name(fake_db, d):
    return (fake_db.profiles.get(d.get("profile_id")) or {}).get("name")


def csv_rows(resp):
    return list(csv.reader(io.StringIO(resp.data.decode("utf-8-sig"))))


def columns(env):
    return [c["name"] for c in env["table"]["columns"]]
