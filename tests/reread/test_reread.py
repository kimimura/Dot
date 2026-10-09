from conftest import wait_for

from core import ai as llm, locks
from helpers import convert, keep_in_library, read_in_builder, teach_acme
from modules.conversion import queue, reading
from modules.documents import repository as documents
from modules.profiles import hints as hint_rules

ACME = ["Invoice No", "Item", "Qty", "Price"]


def doc(client, did):
    return client.get(f"/api/docs/{did}").get_json()


def columns(env):
    return [c["name"] for c in env["table"]["columns"]]


def settled(client, did):
    return wait_for(lambda: (lambda e: e if e["doc"]["stage"] != "rereading" else None)(doc(client, did)))


def taught_and_emailed(client, fake_db, acme_pdf, acme2_pdf):
    # ACME taught in Profile Builder, then a second ACME file comes in by email and is read by its layout
    taught = teach_acme(client, acme_pdf)
    return taught, convert(acme2_pdf)["id"], next(iter(fake_db.profiles.values()))


def improve(fake_db, p):
    # what a user does on the Profiles page: rename a column, keeping the printed name as an alias
    p["columns"] = [{"name": "Invoice No", "kind": "doc"}, {"name": "Item", "kind": "row"},
                    {"name": "Quantity", "kind": "row", "aliases": ["Qty"]}, {"name": "Price", "kind": "row"}]
    fake_db.profiles[p["id"]] = p


def test_a_file_is_re_read_with_the_current_format_by_its_layout_with_no_model(client, fake_db, acme_pdf, acme2_pdf, monkeypatch):
    _, did, p = taught_and_emailed(client, fake_db, acme_pdf, acme2_pdf)
    assert columns(doc(client, did)) == ACME
    improve(fake_db, p)
    monkeypatch.setattr(llm, "get_llm", lambda: (_ for _ in ()).throw(AssertionError("a re-read must not use a model")))
    env = client.post(f"/api/docs/{did}/reread").get_json()
    assert env["doc"]["stage"] == "rereading" and env["changes"][0]["ok"]
    env = settled(client, did)
    assert env["doc"]["stage"] == "converted" and env["doc"]["can_undo_reread"] and env["doc"]["reread_at"]
    assert columns(env) == ["Invoice No", "Item", "Quantity", "Price"]
    assert env["table"]["rows"][0]["Quantity"] == "3" and env["table"]["rows"][0]["Price"] == "100.00"


def test_undo_puts_the_old_sheet_back(client, fake_db, acme_pdf, acme2_pdf):
    _, did, p = taught_and_emailed(client, fake_db, acme_pdf, acme2_pdf)
    improve(fake_db, p)
    client.post(f"/api/docs/{did}/reread")
    settled(client, did)
    env = client.post(f"/api/docs/{did}/reread/undo").get_json()
    assert columns(env) == ACME and not env["doc"]["can_undo_reread"]
    assert columns(doc(client, did)) == ACME
    env = client.post(f"/api/docs/{did}/reread/undo").get_json()
    assert env["changes"] == [{"ok": False, "text": "Nothing to undo"}]


def test_a_file_without_a_saved_format_is_refused(client, orbit_pdf):
    did = keep_in_library(client, orbit_pdf, "orbit.pdf")
    env = client.post(f"/api/docs/{did}/reread").get_json()
    assert env["doc"]["stage"] == "confirmed"
    assert env["changes"] == [{"ok": False, "text": "This file has no saved format to re-read with"}]


def test_a_file_that_no_longer_fits_keeps_its_sheet_and_says_why(client, fake_db, acme_pdf, acme2_pdf, monkeypatch):
    _, did, _ = taught_and_emailed(client, fake_db, acme_pdf, acme2_pdf)
    monkeypatch.setattr(reading, "read_direct", lambda conn, d, prof, texts: (None, None, 'layout changed: "Qty" not found in 1 row'))
    client.post(f"/api/docs/{did}/reread")
    env = settled(client, did)
    assert env["doc"]["stage"] == "converted" and env["doc"]["reread_error"] == (
        "doesn't fit the current ACME format (layout changed: \"Qty\" not found in 1 row); open it in Profile Builder")
    assert columns(env) == ACME and not env["doc"]["can_undo_reread"]


def test_re_read_all_only_touches_that_format(client, fake_db, acme_pdf, acme2_pdf, orbit_pdf):
    first, second, p = taught_and_emailed(client, fake_db, acme_pdf, acme2_pdf)
    other = keep_in_library(client, orbit_pdf, "orbit.pdf")
    improve(fake_db, p)
    r = client.post(f"/api/profiles/{p['id']}/reread").get_json()
    assert r == {"started": 2, "skipped": 0}
    for did in (first, second):
        assert columns(settled(client, did)) == ["Invoice No", "Item", "Quantity", "Price"]
    assert not doc(client, other)["doc"]["reread_at"]


def test_a_file_open_elsewhere_is_skipped_not_waited_for(client, fake_db, acme_pdf, acme2_pdf):
    busy, free, p = taught_and_emailed(client, fake_db, acme_pdf, acme2_pdf)
    lk = locks.take(busy)
    try:
        r = client.post(f"/api/profiles/{p['id']}/reread").get_json()
    finally:
        lk.release()
    assert r == {"started": 1, "skipped": 1}
    settled(client, free)


def test_a_re_read_interrupted_by_a_restart_picks_up_again(client, fake_db, acme_pdf, acme2_pdf):
    _, did, p = taught_and_emailed(client, fake_db, acme_pdf, acme2_pdf)
    improve(fake_db, p)
    fake_db.docs[did].update(stage="rereading", reread_from="converted")
    assert did in documents.pending(None)
    queue.run(did)
    env = doc(client, did)
    assert env["doc"]["stage"] == "converted" and columns(env)[2] == "Quantity"


def test_ordering_requests_are_never_saved_as_hints(client, acme_pdf, monkeypatch):
    class Stub:
        def complete(self, pdf, prompt, kind="extract"):
            if kind != "chat":
                return llm.OfflineAdapter().complete(pdf, prompt, kind)
            return {"reply": "Done.", "intent": "edit", "ops": [{"op": "reorder_cols", "order": ["Item"]}],
                    "hints": [{"scope": "col", "col": "Item", "text": "Always place the item code before the invoice number."},
                              {"scope": "col", "col": "Date", "text": "Use the delivery date, not the order date"}]}
    did = read_in_builder(client, acme_pdf)
    monkeypatch.setattr(llm, "get_llm", lambda: Stub())
    env = client.post(f"/api/docs/{did}/chat", json={"message": "put item code first"}).get_json()
    assert columns(env)[0] == "Item"
    assert [h["text"] for h in env["doc"]["hints"]] == ["Use the delivery date, not the order date"]


def test_the_ordering_filter_keeps_reading_hints():
    blocked = ["Always place the item sequence number before the item code.", "Move Total to the end",
               "Put UOM after Quantity", "Item No. should come first", "Make SKU the last column"]
    kept = ["Use the date after 'Delivery:'", "Item Code is the 7-digit number before the description",
            "Take the first number on the line", "Use the delivery date, not the order date"]
    assert all(hint_rules.about_order(t) for t in blocked)
    assert not any(hint_rules.about_order(t) for t in kept)
