from core import db


def test_errors_are_plain_and_never_speak_as_dot(client, monkeypatch):
    r = client.get("/api/docs/doesnotexist")
    assert (r.status_code, r.get_json()["say"]) == (404, "Not found.")

    def down(tries=1):
        raise db.Unreachable("timeout")
    monkeypatch.setattr(db, "connect", down)
    r = client.get("/api/docs/whatever")
    assert (r.status_code, r.get_json()["say"]) == (503, "Database unreachable — try again in a moment.")
