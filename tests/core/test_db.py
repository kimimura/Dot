import pyodbc

import pdfgen
from core import db, pdftext
from core.ai.offline import OfflineAdapter
from modules.builder import extraction
from modules.documents import repository as documents, work
from modules.outputs import service as outputs

DROPPED = pyodbc.OperationalError("08S01", "[08S01] [Microsoft][ODBC Driver 18 for SQL Server]Communication link failure (10053)")


def test_a_dropped_connection_is_told_apart_from_a_real_database_error():
    assert db.lost(DROPPED)
    assert not db.lost(pyodbc.ProgrammingError("42S22", "Invalid column name 'recipe_json'"))
    assert not db.lost(ValueError("08S01"))


def reading_doc(fake_db):
    pdf = pdfgen.acme(2)
    fake_db.add_submission(None, "s1", "builder")
    d = fake_db.create(None, "acme2.pdf", pdftext.inspect(pdf), "s1", stage="extracting")
    fake_db.pdfs[d["id"]] = pdf
    return d["id"], pdf


def test_a_read_whose_save_meets_a_dropped_connection_is_still_saved(fake_db, monkeypatch):
    did, pdf = reading_doc(fake_db)
    real, calls = documents.save, []

    def flaky(conn, d):
        calls.append(1)
        if len(calls) == 1:
            raise DROPPED
        real(conn, d)
    monkeypatch.setattr(documents, "save", flaky)
    work.run(did, lambda conn, d: extraction.on_extract(conn, OfflineAdapter(), d, pdf))
    assert len(fake_db.docs[did]["table"]["rows"]) == 1 and fake_db.docs[did]["stage"] == "review"


def test_when_the_connection_is_gone_by_the_end_the_result_is_saved_on_a_new_one(fake_db, monkeypatch):
    did, pdf = reading_doc(fake_db)
    real, calls = outputs.refresh, []

    def flaky(conn, d):
        calls.append(1)
        if len(calls) == 1:
            raise DROPPED
        real(conn, d)
    monkeypatch.setattr(outputs, "refresh", flaky)
    work.run(did, lambda conn, d: extraction.on_extract(conn, OfflineAdapter(), d, pdf))
    assert len(calls) == 2 and len(fake_db.docs[did]["table"]["rows"]) == 1
