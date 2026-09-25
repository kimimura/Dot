import json
import sqlite3
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
UPLOADS = DATA / "uploads"
OUTPUTS = DATA / "outputs"
DB_PATH = DATA / "app.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE COLLATE NOCASE,
  created_at TEXT, updated_at TEXT,
  columns_json TEXT DEFAULT '[]',
  fingerprint_json TEXT DEFAULT '{}',
  hints_json TEXT DEFAULT '[]',
  examples_json TEXT DEFAULT '[]',
  signature_json TEXT DEFAULT '{}',
  times_used INTEGER DEFAULT 0,
  last_used_at TEXT
);
CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY,
  filename TEXT, sha256 TEXT, size INTEGER, n_pages INTEGER,
  uploaded_at TEXT, confirmed_at TEXT,
  stage TEXT, error TEXT,
  profile_id TEXT REFERENCES profiles(id) ON DELETE SET NULL,
  has_text_layer INTEGER DEFAULT 0,
  n_rows INTEGER DEFAULT 0, verified_pct REAL,
  state_json TEXT DEFAULT '{}',
  xlsx_path TEXT, csv_path TEXT
);
CREATE INDEX IF NOT EXISTS ix_docs_uploaded ON documents(uploaded_at DESC);
CREATE INDEX IF NOT EXISTS ix_docs_profile ON documents(profile_id);
"""


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def new_id():
    return uuid.uuid4().hex[:12]


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    for d in (DATA, UPLOADS, OUTPUTS):
        d.mkdir(parents=True, exist_ok=True)
    conn = connect()
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def dumps(v):
    return json.dumps(v, ensure_ascii=False)


def loads(s, default):
    if not s:
        return default
    try:
        return json.loads(s)
    except ValueError:
        return default
