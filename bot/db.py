import json
import os
import time
import uuid
from datetime import datetime, timedelta

import pyodbc

SCHEMA = [
    """
    IF OBJECT_ID('profiles', 'U') IS NULL
    CREATE TABLE profiles (
      id NVARCHAR(32) NOT NULL PRIMARY KEY,
      name NVARCHAR(200) NOT NULL UNIQUE,
      created_at NVARCHAR(32), updated_at NVARCHAR(32), last_used_at NVARCHAR(32),
      columns_json NVARCHAR(MAX) DEFAULT '[]',
      fingerprint_json NVARCHAR(MAX) DEFAULT '{}',
      hints_json NVARCHAR(MAX) DEFAULT '[]',
      examples_json NVARCHAR(MAX) DEFAULT '[]',
      signature_json NVARCHAR(MAX) DEFAULT '{}',
      times_used INT DEFAULT 0
    )""",
    """
    IF OBJECT_ID('documents', 'U') IS NULL
    CREATE TABLE documents (
      id NVARCHAR(32) NOT NULL PRIMARY KEY,
      filename NVARCHAR(400), sha256 NVARCHAR(64), size BIGINT, n_pages INT,
      uploaded_at NVARCHAR(32), confirmed_at NVARCHAR(32),
      stage NVARCHAR(32), error NVARCHAR(MAX),
      profile_id NVARCHAR(32) NULL REFERENCES profiles(id) ON DELETE SET NULL,
      has_text_layer BIT DEFAULT 0,
      n_rows INT DEFAULT 0, verified_pct FLOAT NULL,
      state_json NVARCHAR(MAX) DEFAULT '{}',
      pdf_data VARBINARY(MAX) NULL
    )""",
    "IF COL_LENGTH('documents', 'pdf_data') IS NULL"
    " ALTER TABLE documents ADD pdf_data VARBINARY(MAX) NULL",
    "IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='ix_docs_uploaded')"
    " CREATE INDEX ix_docs_uploaded ON documents(uploaded_at DESC)",
    "IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='ix_docs_profile')"
    " CREATE INDEX ix_docs_profile ON documents(profile_id)",
    "IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='ix_docs_sha')"
    " CREATE INDEX ix_docs_sha ON documents(sha256)",
]


class DbNotConfigured(Exception):
    pass


def _env(name, default=""):
    return os.environ.get(name, default).strip()


def configured():
    return bool(_env("DB_SERVER") and _env("DB_NAME"))


def conn_str():
    if not configured():
        raise DbNotConfigured("set DB_SERVER and DB_NAME in .env")
    driver = _env("DB_DRIVER", "ODBC Driver 18 for SQL Server")
    server = _env("DB_SERVER")
    port = _env("DB_PORT")
    parts = [
        f"DRIVER={{{driver}}}",
        f"SERVER={server},{port}" if port else f"SERVER={server}",
        f"DATABASE={_env('DB_NAME')}",
        f"Encrypt={_env('DB_ENCRYPT', 'yes')}",
        f"TrustServerCertificate={_env('DB_TRUST_CERT', 'yes')}",
        f"Connection Timeout={_env('DB_TIMEOUT', '8')}",
        f"ConnectRetryCount={_env('DB_RETRY_COUNT', '0')}",
    ]
    if _env("DB_USER"):
        parts += [f"UID={_env('DB_USER')}", f"PWD={_env('DB_PASSWORD')}"]
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

    def commit(self):
        self.raw.commit()

    def close(self):
        try:
            self.raw.close()
        except Exception:
            pass


class Unreachable(Exception):
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
        for stmt in SCHEMA:
            raw.execute(stmt)
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


def store_pdf(conn, doc_id, data):
    cur = conn.raw.cursor()
    cur.setinputsizes([(pyodbc.SQL_VARBINARY, 0, 0), None])
    cur.execute("UPDATE documents SET pdf_data=? WHERE id=?", pyodbc.Binary(data), doc_id)
    cur.close()


def load_pdf(conn, doc_id):
    r = conn.execute("SELECT pdf_data FROM documents WHERE id=?", (doc_id,)).fetchone()
    return bytes(r["pdf_data"]) if r and r["pdf_data"] else None


