import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


def env(*names, default=""):
    for n in names:
        v = os.environ.get(n, "").strip()
        if v:
            return v
    return default


# ── app ──────────────────────────────────────────────────────────────────────
COMPANION_NAME = env("COMPANION_NAME", default="Dot")
HOST = env("HOST", default="127.0.0.1")
PORT = int(env("PORT", default="5000"))
SERVER_THREADS = 4
ACTIVITY_TIME_FORMAT = "%H:%M:%S"
SERVER_BUSY_MESSAGE = "Busy: all {threads} workers are in use, {waiting} request{s} waiting"
REQUEST_MAX_BYTES = 50 * 1024 * 1024
STATIC_DIR = ROOT / "static"
TEMPLATE_DIR = ROOT / "templates"

# ── database ─────────────────────────────────────────────────────────────────
DB_SERVER = env("DB_SERVER")
DB_PORT = env("DB_PORT")
DB_NAME = env("DB_NAME")
DB_USER = env("DB_USER")
DB_PASSWORD = env("DB_PASSWORD")
DB_DRIVER = env("DB_DRIVER", default="ODBC Driver 18 for SQL Server")
DB_ENCRYPT = env("DB_ENCRYPT", default="yes")
DB_TRUST_CERT = env("DB_TRUST_CERT", default="yes")
DB_TIMEOUT = env("DB_TIMEOUT", default="8")
DB_RETRY_COUNT = env("DB_RETRY_COUNT", default="0")
DB_PROBE_SECONDS = 10.0
DB_PROBE_TIMEOUT = 3
MIGRATIONS = ROOT / "migration"

# ── model ────────────────────────────────────────────────────────────────────
AI_PROVIDER = env("LLM_PROVIDER")
AI_KEY = env("LLM_API_KEY", "GEMINI_API_KEY", "API_KEY")
# tried in this order; when one is used up the next takes over
AI_MODELS = [m.strip() for m in env("LLM_MODELS", "LLM_MODEL", "GEMINI_MODEL").split(",") if m.strip()]
AI_DAILY_RESET_UTC_HOUR = 8
AI_OVERLOAD_REST = 60
AI_RPM = int(env("LLM_RPM", default="15"))
AI_TEMPERATURE = 0.1
AI_CHAT_MAX_REPLY_TOKENS = 16384
AI_MAX_RETRIES = 5
AI_MAX_WAIT = 60
AI_WAIT_BUDGET = 120

# ── PDFs ─────────────────────────────────────────────────────────────────────
PDF_MAX_BYTES = 20 * 1024 * 1024
PDF_MAX_PAGES = 500
PDF_MAX_TOKENS = 150
PDF_WORD_GAP = 0.06

# ── reading with the model ───────────────────────────────────────────────────
EXTRACT_CHUNK_PAGES = 100
EXTRACT_CHUNK_CHARS = 30000
EXTRACT_SCAN_CHUNK_PAGES = 15
EXTRACT_MIN_SPLIT_PAGES = 3
EXTRACT_COVERAGE_OK = 1.0
EXTRACT_MAX_EXTRA_READS = 3

# ── checking values against the PDF ──────────────────────────────────────────
VERIFY_MAX_GAP = 200
VERIFY_MAX_ANCHORS = 80
VERIFY_MIN_ANCHOR = 5
VERIFY_MAX_TAIL_LINES = 12
VERIFY_MIN_WRAPS = 2
VERIFY_LINE_END_SHARE = 0.8
VERIFY_WRAP_REACH = 40
VERIFY_MAX_ROW_JUMP = 200
FIX_FROM_TEXT_SIMILAR = 0.75

# ── reading with a learned layout ────────────────────────────────────────────
LAYOUT_MAX_VARIANTS = 3
LAYOUT_MAX_ROW_LINES = 12
LAYOUT_MAX_TAIL_TOKENS = 3
LAYOUT_SIMILAR = 0.85
LAYOUT_TRUST = 0.85
LAYOUT_FIELD_TRUST = 0.8
LAYOUT_MATCH = 0.97
LAYOUT_MAX_BLOCK_LINES = 6
LAYOUT_LEARN_FROM = 3

# ── formats ──────────────────────────────────────────────────────────────────
MATCH_STRONG = 0.55
MATCH_WEAK = 0.30
MATCH_MARGIN = 0.12
PROFILE_MAX_FP_TOKENS = 300
PROFILE_MAX_FP_DOCS = 20
PROFILE_MAX_HINTS = 30
PROFILE_MAX_EXAMPLES = 3
PROFILE_HINT_MAX_CHARS = 220
PROFILE_CORE_TOKENS_SHOWN = 24
PROFILE_NAME_MAX_CHARS = 60
PROFILE_COLUMN_HINT_MAX_CHARS = 200
PROFILE_RULE_MAX_CHARS = 300
PROFILE_MAX_ALIASES = 10
PROFILE_DOCS_SHOWN = 20

# ── documents and chat ───────────────────────────────────────────────────────
UNDO_DEPTH = 10
CHAT_MAX_CHARS = 2000
CHAT_MAX_UNDO_STEPS = 10
REREAD_MIN_MATCHED = 0.9
REREAD_LOOKAHEAD = 8
REREAD_SIMILAR = 0.85
LIBRARY_LIST_LIMIT = 500

# ── stats ────────────────────────────────────────────────────────────────────
STATS_TOP_FORMATS = 8
STATS_WEEK_DAYS = 7
STATS_CHART_DAYS = 14

# ── standard output ──────────────────────────────────────────────────────────
OUTPUT_DATE_ORDER = "dmy"
OUTPUT_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
OUTPUT_SENDER_COLUMN = "Received From"
OUTPUT_SENDER_KEY = "received_from"
OUTPUT_UNIDENTIFIED = "Unidentified"

# ── email intake ─────────────────────────────────────────────────────────────
EMAIL_INTAKE_TOKEN = env("EMAIL_INTAKE_TOKEN")
EMAIL_ALERT_URL = env("EMAIL_ALERT_URL")
EMAIL_ALERT_TIMEOUT = 30
EMAIL_ALERT_TRIES = 3
EMAIL_ALERT_RETRY_SECONDS = 30
EMAIL_POLL_SECONDS = 5
EMAIL_MAX_WAIT_SECONDS = 3 * 60 * 60
EMAIL_STAMP_FORMAT = "%Y%m%d_%H%M%S"
EMAIL_FILE_NAME = "{format}_SalesOrder_{stamp}"
EMAIL_SUBJECT = "{n} PDF{s} Received"
EMAIL_FILE_LINE = "{rows} line{s} · {file}"
EMAIL_UNIDENTIFIED = "Unidentified"
EMAIL_UNREADABLE = "Could not be read"
EMAIL_UNFINISHED = "Still processing"
