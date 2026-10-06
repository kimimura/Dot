import json
import re
import time
import uuid
from datetime import datetime, timedelta

import pyodbc

import config


class DbNotConfigured(Exception):
    pass


class Unreachable(Exception):
    pass


APPLIED_TABLE = ("IF OBJECT_ID('schema_migrations', 'U') IS NULL "
                 "CREATE TABLE schema_migrations (name NVARCHAR(200) NOT NULL PRIMARY KEY, applied_at NVARCHAR(32) NOT NULL)")


def statements(path):
    return [b.strip() for b in re.split(r"(?im)^\s*GO\s*$", path.read_text(encoding="utf-8")) if b.strip()]


def pending(applied):
    return [f for f in sorted(config.MIGRATIONS.glob("*.sql")) if f.name not in applied]


def configured():
    return bool(config.DB_SERVER and config.DB_NAME)


def where():
    return f"{config.DB_SERVER}/{config.DB_NAME}"


def conn_str(timeout=None):
    if not configured():
        raise DbNotConfigured("set DB_SERVER and DB_NAME in .env")
    parts = [
        f"DRIVER={{{config.DB_DRIVER}}}",
        f"SERVER={config.DB_SERVER},{config.DB_PORT}" if config.DB_PORT else f"SERVER={config.DB_SERVER}",
        f"DATABASE={config.DB_NAME}",
        f"Encrypt={config.DB_ENCRYPT}",
        f"TrustServerCertificate={config.DB_TRUST_CERT}",
        f"Connection Timeout={timeout or config.DB_TIMEOUT}",
        f"ConnectRetryCount={config.DB_RETRY_COUNT}",
    ]
    if config.DB_USER:
        parts += [f"UID={config.DB_USER}", f"PWD={config.DB_PASSWORD}"]
    else:
        parts.append("Trusted_Connection=yes")
    return ";".join(parts)


class Row(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)


class Cursor:
    def __init__(self, cur):
        self.cur = cur
        self.cols = [c[0] for c in cur.description] if cur.description else []

    def fetchone(self):
        r = self.cur.fetchone()
        return Row(zip(self.cols, r)) if r else None

    def fetchall(self):
        return [Row(zip(self.cols, r)) for r in self.cur.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())


class Conn:
    def __init__(self, raw):
        self.raw = raw

    def execute(self, sql, params=()):
        return Cursor(self.raw.execute(sql, tuple(params)) if params else self.raw.execute(sql))

    def write_blob(self, sql, blob, *params):
        cur = self.raw.cursor()
        cur.setinputsizes([(pyodbc.SQL_VARBINARY, 0, 0)] + [None] * len(params))
        cur.execute(sql, pyodbc.Binary(blob), *params)
        cur.close()

    def commit(self):
        self.raw.commit()

    def close(self):
        try:
            self.raw.close()
        except Exception:
            pass


def connect(tries=1):
    last = None
    for n in range(tries):
        try:
            return Conn(pyodbc.connect(conn_str(), autocommit=False))
        except pyodbc.Error as e:
            last = e
            if n + 1 < tries:
                time.sleep(1)
    raise Unreachable(str(last).split("]")[-1].strip()[:150])


def init_db():
    raw = pyodbc.connect(conn_str(), autocommit=True)
    try:
        raw.execute(APPLIED_TABLE)
        applied = {r[0] for r in raw.execute("SELECT name FROM schema_migrations").fetchall()}
        for f in pending(applied):
            for stmt in statements(f):
                raw.execute(stmt)
            raw.execute("INSERT INTO schema_migrations(name, applied_at) VALUES (?, ?)", f.name, now())
    finally:
        raw.close()


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def days_ago(n):
    return (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%dT%H:%M:%S")


def new_id():
    return uuid.uuid4().hex[:12]


def dumps(v):
    return json.dumps(v, ensure_ascii=False)


def loads(s, default):
    if not s:
        return default
    try:
        return json.loads(s)
    except ValueError:
        return default


_probe = {"at": 0.0, "result": "unknown"}


def probe():
    if time.time() - _probe["at"] < config.DB_PROBE_SECONDS:
        return _probe["result"]
    try:
        c = pyodbc.connect(conn_str(timeout=config.DB_PROBE_TIMEOUT), autocommit=True, timeout=config.DB_PROBE_TIMEOUT)
        c.close()
        _probe["result"] = "ok"
    except DbNotConfigured as e:
        _probe["result"] = f"not configured: {e}"
    except Exception:
        _probe["result"] = "unreachable"
    _probe["at"] = time.time()
    return _probe["result"]
