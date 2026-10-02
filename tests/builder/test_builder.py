from core import ai
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
