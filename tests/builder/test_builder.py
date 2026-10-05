from core import ai
from core.ai import errors
from core.ai.errors import Truncated
from helpers import ACME_COLUMNS, columns, upload


def builder_doc(client, acme_pdf):
    did = upload(client, acme_pdf).headers["X-Dot-Document"]
    env = client.post(f"/api/docs/{did}/review").get_json()
    assert env["doc"]["stage"] == "review" and columns(env) == ACME_COLUMNS
    return did


def test_a_column_dropped_by_hand_stays_dropped(client, acme_pdf):
    did = builder_doc(client, acme_pdf)
    client.post(f"/api/docs/{did}/ops", json={"ops": [{"op": "drop_col", "col": "Price"}]})
    assert "Price" not in columns(client.get(f"/api/docs/{did}").get_json())
    env = client.post(f"/api/docs/{did}/chat", json={"message": "drop Customer"}).get_json()
    assert "Price" not in columns(env) and "Customer" not in columns(env)


def test_a_cell_typed_by_hand_is_saved(client, acme_pdf):
    did = builder_doc(client, acme_pdf)
    client.post(f"/api/docs/{did}/ops", json={"ops": [{"op": "set_cell", "row": 1, "col": "Qty", "value": "6"}]})
    env = client.get(f"/api/docs/{did}").get_json()
    assert env["table"]["rows"][1]["Qty"] == "6"


def test_revert_in_chat_is_a_real_undo(client, acme_pdf):
    did = builder_doc(client, acme_pdf)
    env = client.post(f"/api/docs/{did}/chat", json={"message": "rename Item to Item Code"}).get_json()
    assert "Item Code" in columns(env)
    env = client.post(f"/api/docs/{did}/chat", json={"message": "No, that's wrong, revert please"}).get_json()
    assert columns(env) == ACME_COLUMNS and [c["text"] for c in env["changes"]] == ["Undid the last change"]
    assert columns(client.get(f"/api/docs/{did}").get_json()) == ACME_COLUMNS
    env = client.post(f"/api/docs/{did}/chat", json={"message": "undo"}).get_json()
    assert [c["text"] for c in env["changes"]] == ["Nothing to undo"]


def test_the_undo_button_is_saved_too(client, acme_pdf):
    did = builder_doc(client, acme_pdf)
    client.post(f"/api/docs/{did}/ops", json={"ops": [{"op": "drop_col", "col": "Price"}]})
    client.post(f"/api/docs/{did}/undo")
    assert columns(client.get(f"/api/docs/{did}").get_json()) == ACME_COLUMNS


def test_columns_named_by_letter_are_the_ones_the_user_saw(client, acme_pdf, monkeypatch):
    class Stub:
        def complete(self, pdf, prompt, kind="extract"):
            if kind != "chat":
                return ai.OfflineAdapter().complete(pdf, prompt, kind)
            return {"reply": "Done.", "intent": "edit", "hints": [], "ops": [
                {"op": "merge_cols", "cols": ["B", "C"], "into": "Date And Customer"},
                {"op": "rename_col", "col": "D", "new_name": "Amount"},
                {"op": "drop_col", "col": "E"}]}
    did = builder_doc(client, acme_pdf)
    monkeypatch.setattr(ai, "get_llm", lambda: Stub())
    env = client.post(f"/api/docs/{did}/chat", json={"message": "merge B and C, call D Amount, drop E"}).get_json()
    assert columns(env) == ["Invoice No", "Date And Customer", "Amount", "Description", "Qty", "Price"]
    assert all(c["ok"] for c in env["changes"])


def test_values_dot_types_are_checked_and_values_you_type_are_trusted(client, acme_pdf, monkeypatch):
    class Stub:
        def complete(self, pdf, prompt, kind="extract"):
            if kind != "chat":
                return ai.OfflineAdapter().complete(pdf, prompt, kind)
            return {"reply": "Done.", "intent": "edit", "hints": [], "ops": [{"op": "set_col", "col": "Qty", "values": ["73519", "84620"]}]}
    did = builder_doc(client, acme_pdf)
    client.post(f"/api/docs/{did}/ops", json={"ops": [{"op": "set_cell", "row": 0, "col": "Price", "value": "1234.56"}]})
    monkeypatch.setattr(ai, "get_llm", lambda: Stub())
    cells = client.post(f"/api/docs/{did}/chat", json={"message": "qty should be 73519 and 84620"}).get_json()["table"]["verification"]["cells"]
    assert (cells["0|Qty"], cells["1|Qty"], cells["0|Price"]) == ("miss", "miss", "edited")


def test_a_cut_off_reply_changes_nothing_and_says_so(client, acme_pdf, monkeypatch):
    class Stub:
        def complete(self, pdf, prompt, kind="extract"):
            if kind != "chat":
                return ai.OfflineAdapter().complete(pdf, prompt, kind)
            raise Truncated(errors.CUT_OFF)
    did = builder_doc(client, acme_pdf)
    monkeypatch.setattr(ai, "get_llm", lambda: Stub())
    env = client.post(f"/api/docs/{did}/chat", json={"message": "move Total into ROWS"}).get_json()
    assert "cut off before it finished, so nothing changed" in env["bot"]["say"] and columns(env) == ACME_COLUMNS


class Rereader:
    # chat asks for a re-read of column G; the re-read answers with what the PDF prints
    def __init__(self, ops, printed):
        self.ops, self.printed = ops, printed

    def complete(self, pdf, prompt, kind="extract"):
        if kind == "chat":
            return {"reply": "Done.", "intent": "edit", "hints": [], "ops": self.ops}
        if "re-reading some columns" in prompt:
            return {"rows": self.printed}
        return ai.OfflineAdapter().complete(pdf, prompt, kind)


def test_asking_dot_to_re_read_a_column_takes_it_from_the_pdf(client, acme_pdf, monkeypatch):
    did = builder_doc(client, acme_pdf)
    rows = client.get(f"/api/docs/{did}").get_json()["table"]["rows"]
    printed = [[r["Item"], r["Qty"]] for r in rows]
    monkeypatch.setattr(ai, "get_llm", lambda: Rereader([{"op": "set_col", "col": "Qty", "values": ["99999", "88888"]}], printed))
    client.post(f"/api/docs/{did}/chat", json={"message": "qty is 99999 and 88888"})
    monkeypatch.setattr(ai, "get_llm", lambda: Rereader([{"op": "reread_cols", "cols": ["G"]}], printed))
    env = client.post(f"/api/docs/{did}/chat", json={"message": "column G is wrong, check the PDF"}).get_json()
    assert [r["Qty"] for r in env["table"]["rows"]] == [r["Qty"] for r in rows]
    assert env["changes"][0] == {"ok": True, "text": 'Re-read "Qty" from the PDF (2 of 2 rows)'}


def test_re_read_from_pdf_in_the_column_menu(client, acme_pdf, monkeypatch):
    did = builder_doc(client, acme_pdf)
    rows = client.get(f"/api/docs/{did}").get_json()["table"]["rows"]
    monkeypatch.setattr(ai, "get_llm", lambda: Rereader([], [[r["Item"], "7.50" if i else r["Price"]] for i, r in enumerate(rows)]))
    env = client.post(f"/api/docs/{did}/ops", json={"ops": [{"op": "reread_cols", "cols": ["Price"]}]}).get_json()
    assert [r["Price"] for r in env["table"]["rows"]] == [r["Price"] for r in rows]
    assert env["changes"] == [{"ok": False, "text": 'Nothing changed in "Price": the values that differed from the sheet don\'t match the PDF'}]


def kept_changes(env):
    return [c["text"] for t in env["transcript"] if t["who"] == "sys" for c in t["changes"]]


def test_what_each_edit_did_stays_in_the_conversation(client, acme_pdf):
    did = builder_doc(client, acme_pdf)
    client.post(f"/api/docs/{did}/chat", json={"message": "rename Item to Item Code"})
    env = client.post(f"/api/docs/{did}/chat", json={"message": "drop Customer"}).get_json()
    assert kept_changes(env) == ['Renamed "Item" to "Item Code"', 'Dropped "Customer"']
    who = [t["who"] for t in client.get(f"/api/docs/{did}").get_json()["transcript"]]
    assert who[-6:] == ["user", "bot", "sys", "user", "bot", "sys"]


def test_cells_typed_by_hand_are_not_added_to_the_conversation(client, acme_pdf):
    did = builder_doc(client, acme_pdf)
    client.post(f"/api/docs/{did}/ops", json={"ops": [{"op": "set_cell", "row": 1, "col": "Qty", "value": "6"}]})
    env = client.post(f"/api/docs/{did}/ops", json={"ops": [{"op": "drop_col", "col": "Price"}]}).get_json()
    assert kept_changes(env) == ['Dropped "Price"']


def save_as(client, did, name):
    for option, extra in (("yes", {}), ("yes", {}), ("submit", {"name": name})):
        env = client.post(f"/api/docs/{did}/answer", json={"option": option, **extra}).get_json()
    return env


def profile_named(client, name):
    return next((p for p in client.get("/api/profiles").get_json()["profiles"] if p["name"] == name), None)


def test_a_new_format_is_saved_and_recognised_next_time(client, acme_pdf, acme2_pdf):
    did = builder_doc(client, acme_pdf)
    env = save_as(client, did, "ACME")
    assert env["doc"]["stage"] == "confirmed" and env["doc"]["profile_name"] == "ACME"
    p = profile_named(client, "ACME")
    assert [c["name"] for c in p["columns"]] == ACME_COLUMNS and p["n_docs"] == 1
    assert upload(client, acme2_pdf).headers["X-Dot-Format"] == "ACME"


def test_a_name_already_taken_is_asked_again(client, acme_pdf, orbit_pdf):
    save_as(client, builder_doc(client, acme_pdf), "ACME")
    did = upload(client, orbit_pdf, "orbit.pdf").headers["X-Dot-Document"]
    client.post(f"/api/docs/{did}/review")
    env = save_as(client, did, "acme")
    assert env["doc"]["stage"] == "naming" and "**ACME**" in env["bot"]["say"]
    assert [o["id"] for o in env["bot"]["options"]] == ["use_existing", "back"]
    assert len(client.get("/api/profiles").get_json()["profiles"]) == 1


def test_deleting_a_file_makes_its_format_forget_it(client, acme_pdf):
    did = builder_doc(client, acme_pdf)
    save_as(client, did, "ACME")
    assert client.delete(f"/api/docs/{did}").status_code == 200
    assert client.get(f"/api/docs/{did}").status_code == 404
    assert profile_named(client, "ACME")["n_docs"] == 0


def test_a_deleted_format_is_gone(client, acme_pdf):
    save_as(client, builder_doc(client, acme_pdf), "ACME")
    assert client.delete(f"/api/profiles/{profile_named(client, 'ACME')['id']}").status_code == 200
    assert profile_named(client, "ACME") is None


def test_dot_fixing_row_2_changes_the_row_you_see_as_2(client, acme_pdf, monkeypatch):

    class Stub:
        def complete(self, pdf, prompt, kind="extract"):
            if kind != "chat":
                return ai.OfflineAdapter().complete(pdf, prompt, kind)
            assert "\n2 | " in prompt
            return {"reply": "Done.", "intent": "edit", "ops": [{"op": "set_cell", "row": 2, "col": "Qty", "value": "6"}], "hints": []}
    did = builder_doc(client, acme_pdf)
    monkeypatch.setattr(ai, "get_llm", lambda: Stub())
    env = client.post(f"/api/docs/{did}/chat", json={"message": "row 2 quantity should be 6"}).get_json()
    assert [r["Qty"] for r in env["table"]["rows"]] == ["10", "6"]
