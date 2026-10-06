import pyodbc
import pytest

import config
from core import db


class Result:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def fetchall(self):
        return self.rows


class FakeServer:
    def __init__(self):
        self.applied, self.ran = {}, []

    def connect(self, *args, **kwargs):
        return FakeRaw(self)


class FakeRaw:
    def __init__(self, server):
        self.server = server

    def execute(self, sql, *params):
        if "CREATE TABLE schema_migrations" in sql:
            return Result()
        if sql.startswith("SELECT name FROM schema_migrations"):
            return Result((name,) for name in self.server.applied)
        if sql.startswith("INSERT INTO schema_migrations"):
            self.server.applied[params[0]] = params[1]
            return Result()
        if "BROKEN" in sql:
            raise pyodbc.Error("statement failed")
        self.server.ran.append(sql)
        return Result()

    def close(self):
        pass


@pytest.fixture
def server(monkeypatch, tmp_path):
    fake = FakeServer()
    monkeypatch.setattr(config, "MIGRATIONS", tmp_path)
    monkeypatch.setattr(db, "conn_str", lambda timeout=None: "")
    monkeypatch.setattr(pyodbc, "connect", fake.connect)
    return fake


def write(folder, name, *statements):
    (folder / name).write_text("\nGO\n".join(statements) + "\nGO\n", encoding="utf-8")


def test_each_migration_file_runs_once_and_never_again(server, tmp_path):
    write(tmp_path, "001_a.sql", "CREATE A", "ALTER A")
    write(tmp_path, "002_b.sql", "DROP B")
    db.init_db()
    db.init_db()
    assert server.ran == ["CREATE A", "ALTER A", "DROP B"]
    assert sorted(server.applied) == ["001_a.sql", "002_b.sql"]


def test_only_a_newly_added_file_runs_at_the_next_start(server, tmp_path):
    write(tmp_path, "001_a.sql", "CREATE A")
    db.init_db()
    write(tmp_path, "002_b.sql", "DROP B")
    db.init_db()
    assert server.ran == ["CREATE A", "DROP B"]


def test_a_file_that_fails_part_way_runs_again_at_the_next_start(server, tmp_path):
    write(tmp_path, "001_a.sql", "CREATE A", "BROKEN")
    with pytest.raises(pyodbc.Error):
        db.init_db()
    assert server.applied == {}
    write(tmp_path, "001_a.sql", "CREATE A", "FIXED")
    db.init_db()
    assert server.ran == ["CREATE A", "CREATE A", "FIXED"] and list(server.applied) == ["001_a.sql"]
