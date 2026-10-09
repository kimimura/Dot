from flask import abort

import config
from core import db
from core.errors import Refused
from modules.documents import repository as documents
from modules.profiles import matching, repository as profiles

VIEW_KEYS = ("id", "name", "created_at", "updated_at", "columns", "hints", "signature")


def view(conn, p, with_docs=False):
    v = {k: p[k] for k in VIEW_KEYS}
    v["core_tokens"] = matching.core_tokens(p)
    v["n_docs"] = int((p.get("fingerprint") or {}).get("n_docs", 0))
    v["example"] = (p.get("examples") or [None])[0]
    v["reads_directly"] = bool((p.get("layout") or {}).get("variants"))
    v["layout_problem"] = None if v["reads_directly"] else (p.get("layout") or {}).get("last_problem")
    if with_docs:
        v["documents"] = documents.docs_for_profile(conn, p["id"])
    return v


def list_all():
    conn = db.connect()
    out = [view(conn, p) for p in profiles.list_all(conn)]
    conn.close()
    return out


def get(pid):
    conn = db.connect()
    p = profiles.get(conn, pid)
    if not p:
        conn.close()
        abort(404)
    v = view(conn, p, with_docs=True)
    conn.close()
    return v


def create(name, columns):
    name = str(name or "").strip()
    if not name:
        raise Refused(400, "no name", "Give the profile a name.")
    conn = db.connect()
    if profiles.by_name(conn, name):
        conn.close()
        raise Refused(409, "exists", f"A profile named {name} already exists.")
    p = profiles.create(conn, name, columns or [])
    conn.commit()
    v = view(conn, p)
    conn.close()
    return v


def _clean_columns(raw):
    cols, seen = [], set()
    for c in raw:
        n = str(c.get("name", "")).strip()[:config.PROFILE_NAME_MAX_CHARS]
        if n and n.lower() not in seen:
            seen.add(n.lower())
            aliases = [str(a).strip()[:config.PROFILE_NAME_MAX_CHARS] for a in (c.get("aliases") or []) if str(a).strip()]
            cols.append({"name": n, "kind": "doc" if c.get("kind") == "doc" else "row",
                         "hint": str(c.get("hint", "")).strip()[:config.PROFILE_COLUMN_HINT_MAX_CHARS],
                         "seen": int(c.get("seen", 0) or 0), "aliases": aliases[:config.PROFILE_MAX_ALIASES]})
    return cols


def _clean_rules(raw):
    return [{"text": str(h.get("text", "")).strip()[:config.PROFILE_RULE_MAX_CHARS], "added_at": h.get("added_at") or db.now()}
            for h in raw if str(h.get("text", "")).strip()]


def update(pid, body):
    conn = db.connect()
    p = profiles.get(conn, pid)
    if not p:
        conn.close()
        abort(404)
    if "name" in body:
        name = str(body["name"]).strip()
        other = profiles.by_name(conn, name)
        if not name or (other and other["id"] != pid):
            conn.close()
            raise Refused(409, "name", f"A profile named {name} already exists." if name else "Give it a name.")
        p["name"] = name
    if "columns" in body and isinstance(body["columns"], list):
        p["columns"] = _clean_columns(body["columns"])
    if "hints" in body and isinstance(body["hints"], list):
        p["hints"] = _clean_rules(body["hints"])
    # saving a format here is an edit like confirming a file for it: it becomes the format edited last
    profiles.save(conn, p, edited=True)
    conn.commit()
    v = view(conn, profiles.get(conn, pid), with_docs=True)
    conn.close()
    return v


def delete(pid):
    conn = db.connect()
    profiles.delete(conn, pid)
    conn.commit()
    conn.close()
