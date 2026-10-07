import copy
import math
import os
import queue
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["LLM_PROVIDER"] = "offline"

from modules.documents import repository as documents  # noqa: E402
from modules.outputs import repository as outputs  # noqa: E402
from modules.profiles import repository as profiles  # noqa: E402
from modules.submissions import repository as submissions  # noqa: E402
from core import ai, db, jobs, pdftext  # noqa: E402
import pdfgen  # noqa: E402


class FakeConn:
    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass

    def execute(self, sql, args=()):
        raise AssertionError("real SQL reached the fake database: " + sql[:60])


class FakeDb:
    # in-memory stand-in for SQL Server: same functions, same document and profile shapes
    def __init__(self):
        self.docs, self.pdfs, self.profiles, self.submissions, self.outputs = {}, {}, {}, {}, {}

    def add_submission(self, conn, sid, source, sender="", stamp=None, status=None):
        assert sid not in self.submissions, "submission ids are unique"
        self.submissions[sid] = {"id": sid, "source": source, "sender": sender, "received_at": db.now(),
                                 "stamp": stamp, "status": status, "error": None, "sent_at": None}

    def finish_submission(self, conn, sid, status, error=None):
        self.submissions[sid].update(status=status, error=error, sent_at=db.now())

    def new_document(self, filename, info):
        sid = db.new_id()
        self.add_submission(None, sid, "builder")
        return self.create(None, filename, info, sid)

    def create(self, conn, filename, info, submission_id, stage="identify", position=0):
        assert submission_id in self.submissions, "a document needs its submission first"
        d = {"id": db.new_id(), "filename": filename, "sha256": info.sha256, "size": info.size, "n_pages": info.n_pages,
             "uploaded_at": db.now(), "confirmed_at": None, "stage": stage, "error": None, "profile_id": None,
             "has_text_layer": info.has_text_layer, "n_rows": 0, "verified_pct": None, "submission_id": submission_id,
             "position": position, "auto_how": None, "read_note": None}
        for k, v in documents.STATE_DEFAULTS.items():
            d[k] = copy.deepcopy(v)
        d["tokens"], d["structural"] = info.tokens, info.structural
        self.docs[d["id"]] = d
        time.sleep(0.002)
        return copy.deepcopy(d)

    def get(self, conn, did):
        return copy.deepcopy(self.docs.get(did))

    def save(self, conn, d):
        d = copy.deepcopy(d)
        ver = d.get("verification") or {}
        d["n_rows"] = len(d["table"]["rows"]) if d.get("table") else 0
        d["verified_pct"] = math.floor(1000.0 * ver["verified"] / ver["total"]) / 10 if ver.get("checked") and ver.get("total") else None
        self.docs[d["id"]] = d

    def _latest(self, sha, exclude, stages=None):
        hits = [d for d in self.docs.values() if d["sha256"] == sha and d["id"] != exclude
                and (stages is None or (d["stage"] in stages and d.get("table")))]
        hits.sort(key=lambda d: d["uploaded_at"], reverse=True)
        if stages:
            hits.sort(key=lambda d: d["stage"] != "confirmed")
        return copy.deepcopy(hits[0]) if hits else None

    def list_submission(self, conn, sid):
        out = []
        for d in sorted(self.docs.values(), key=lambda d: (d["position"], d["uploaded_at"], d["filename"])):
            if d.get("submission_id") == sid:
                row = {k: d.get(k) for k in ("id", "filename", "stage", "error", "n_pages", "n_rows", "verified_pct",
                                             "has_text_layer", "profile_id", "auto_how", "read_note", "uploaded_at")}
                row["profile_name"] = (self.profiles.get(d.get("profile_id")) or {}).get("name")
                out.append(row)
        return out

    def list_docs(self, conn, q=None, unfinished=False, limit=500):
        out = []
        for d in sorted(self.docs.values(), key=lambda d: d["uploaded_at"], reverse=True):
            if unfinished and d["stage"] not in documents.UNFINISHED:
                continue
            row = {k: d.get(k) for k in ("id", "filename", "uploaded_at", "confirmed_at", "stage", "profile_id", "n_pages",
                                         "n_rows", "verified_pct", "has_text_layer")}
            row["profile_name"] = (self.profiles.get(d.get("profile_id")) or {}).get("name")
            sub = self.submissions.get(d.get("submission_id")) or {}
            row["source"], row["sender"] = sub.get("source"), sub.get("sender")
            row["has_output"] = d["stage"] in ("confirmed", "converted", "rereading")
            row["teaches"] = bool(d.get("profile_id")) and d["stage"] == "confirmed"
            row["teachers"] = self.teachers(conn, d.get("profile_id"))
            out.append(row)
        return out[:limit]

    def teachers(self, conn, pid):
        return sum(1 for d in self.docs.values() if pid and d.get("profile_id") == pid and d["stage"] == "confirmed")

    def add_profile(self, name, columns, pdf_bytes):
        info = pdftext.inspect(pdf_bytes)
        p = {"id": db.new_id(), "name": name, "columns": [{"name": c, "kind": k, "seen": 1} for c, k in columns],
             "fingerprint": {"tokens": {w: 1 for w in info.tokens}, "n_docs": 1, "structural": info.structural},
             "hints": [], "examples": [], "signature": {}, "created_at": db.now(), "updated_at": db.now(),
             "times_used": 1, "last_used_at": None}
        self.profiles[p["id"]] = p
        return p

    def create_profile(self, conn, name, columns=None, signature=None):
        p = {"id": db.new_id(), "name": name.strip(), "columns": columns or [],
             "fingerprint": {"tokens": {}, "n_docs": 0, "structural": {}}, "hints": [], "examples": [], "signature": signature or {},
             "created_at": db.now(), "updated_at": db.now(), "times_used": 0, "last_used_at": None, "layout": None}
        self.profiles[p["id"]] = p
        return copy.deepcopy(p)

    def confirmed_ids(self, conn, pid, exclude):
        return [d["id"] for d in self.docs.values() if d.get("profile_id") == pid and d["stage"] == "confirmed" and d["id"] != exclude]

    def install(self, mp):
        mp.setattr(db, "connect", lambda tries=1: FakeConn())
        mp.setattr(documents, "store_pdf", lambda conn, did, data: self.pdfs.__setitem__(did, data))
        mp.setattr(documents, "load_pdf", lambda conn, did: self.pdfs[did])
        mp.setattr(documents, "create", self.create)
        mp.setattr(documents, "get", self.get)
        mp.setattr(documents, "save", self.save)
        mp.setattr(documents, "by_sha", lambda conn, sha, exclude=None: self._latest(sha, exclude))
        mp.setattr(documents, "reusable", lambda conn, sha, exclude=None: self._latest(sha, exclude, ("confirmed", "converted")))
        mp.setattr(documents, "delete", lambda conn, did: (self.docs.pop(did, None), self.pdfs.pop(did, None)))
        mp.setattr(documents, "list_submission", self.list_submission)
        mp.setattr(documents, "list_docs", self.list_docs)
        mp.setattr(documents, "confirmed_ids", self.confirmed_ids)
        mp.setattr(documents, "teachers", self.teachers)
        mp.setattr(documents, "pending", lambda conn: [d["id"] for d in self.docs.values() if d["stage"] in ("queued", "converting", "rereading")])
        mp.setattr(documents, "rereadable", lambda conn, pid: [d["id"] for d in sorted(self.docs.values(), key=lambda d: d["uploaded_at"])
                                                             if d.get("profile_id") == pid and d["stage"] in ("confirmed", "converted")])
        mp.setattr(documents, "docs_for_profile", lambda conn, pid, limit=20: [
            {k: d.get(k) for k in ("id", "filename", "uploaded_at", "confirmed_at", "n_rows")}
            for d in self.docs.values() if d.get("profile_id") == pid][:limit])
        mp.setattr(profiles, "list_all", lambda conn: [copy.deepcopy(p) for p in sorted(self.profiles.values(), key=lambda p: p["name"])])
        mp.setattr(profiles, "get", lambda conn, pid: copy.deepcopy(self.profiles.get(pid)))
        mp.setattr(profiles, "by_name", lambda conn, name: copy.deepcopy(
            next((p for p in self.profiles.values() if p["name"].lower() == str(name).lower()), None)))
        mp.setattr(profiles, "save", lambda conn, p: self.profiles.__setitem__(p["id"], copy.deepcopy(p)))
        mp.setattr(profiles, "create", self.create_profile)
        mp.setattr(profiles, "delete", lambda conn, pid: self.profiles.pop(pid, None))
        mp.setattr(submissions, "create", self.add_submission)
        mp.setattr(submissions, "get", lambda conn, sid: copy.deepcopy(self.submissions.get(sid)))
        mp.setattr(submissions, "waiting_emails", lambda conn: [k for k, s in self.submissions.items()
                                                                if s["source"] == "email" and s["status"] == "waiting"])
        mp.setattr(submissions, "finish", self.finish_submission)
        mp.setattr(outputs, "get", lambda conn, did, version: copy.deepcopy(self.outputs.get((did, version))))
        mp.setattr(outputs, "save_current", lambda conn, did, chain, at, data: self.outputs.__setitem__((did, "current"), copy.deepcopy(data)))
        mp.setattr(outputs, "keep_sent", lambda conn, did, chain, at, data: self.outputs.setdefault((did, "sent"), copy.deepcopy(data)))
        mp.setattr(outputs, "clear_current", lambda conn, did: self.outputs.pop((did, "current"), None))
        mp.setattr(ai, "get_llm", lambda: ai.OfflineAdapter())
        return self


@pytest.fixture
def fake_db(monkeypatch):
    yield FakeDb().install(monkeypatch)
    # background work a test left behind must not outlive its fake database and reach the real one
    left = []
    while True:
        try:
            left.append(jobs._q.get_nowait()[0])
        except queue.Empty:
            break
    with jobs._guard:
        jobs._queued.difference_update(left)
    end = time.time() + 30
    while (jobs._queued or jobs._active) and time.time() < end:
        time.sleep(0.02)


@pytest.fixture
def client(fake_db):
    import app as app_module
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


@pytest.fixture(scope="session")
def acme_pdf():
    return pdfgen.acme(1)


@pytest.fixture(scope="session")
def acme2_pdf():
    return pdfgen.acme(2)


@pytest.fixture(scope="session")
def orbit_pdf():
    return pdfgen.orbit()


def wait_for(check, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        v = check()
        if v:
            return v
        time.sleep(0.05)
    raise AssertionError("timed out waiting")
