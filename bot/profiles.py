import math
from collections import Counter

from . import db

STRONG, WEAK, MARGIN = 0.55, 0.30, 0.12
MAX_FP_TOKENS = 300
MAX_FP_DOCS = 20
MAX_HINTS = 30
MAX_EXAMPLES = 3


# ── storage ──────────────────────────────────────────────────────────────────

def _row_to_profile(r):
    return {
        "id": r["id"], "name": r["name"],
        "created_at": r["created_at"], "updated_at": r["updated_at"],
        "columns": db.loads(r["columns_json"], []),
        "fingerprint": db.loads(r["fingerprint_json"], {}),
        "hints": db.loads(r["hints_json"], []),
        "examples": db.loads(r["examples_json"], []),
        "signature": db.loads(r["signature_json"], {}),
        "times_used": r["times_used"], "last_used_at": r["last_used_at"],
    }


def list_all(conn):
    rows = conn.execute("SELECT * FROM profiles ORDER BY name COLLATE NOCASE").fetchall()
    return [_row_to_profile(r) for r in rows]


def get(conn, pid):
    r = conn.execute("SELECT * FROM profiles WHERE id=?", (pid,)).fetchone()
    return _row_to_profile(r) if r else None


def by_name(conn, name):
    r = conn.execute("SELECT * FROM profiles WHERE name=? COLLATE NOCASE", (name,)).fetchone()
    return _row_to_profile(r) if r else None


def create(conn, name, columns=None, signature=None):
    pid = db.new_id()
    ts = db.now()
    conn.execute(
        "INSERT INTO profiles(id,name,created_at,updated_at,columns_json,fingerprint_json,signature_json)"
        " VALUES(?,?,?,?,?,?,?)",
        (pid, name.strip(), ts, ts, db.dumps(columns or []),
         db.dumps({"tokens": {}, "n_docs": 0, "structural": {}}), db.dumps(signature or {})),
    )
    return get(conn, pid)


def save(conn, p):
    conn.execute(
        "UPDATE profiles SET name=?, updated_at=?, columns_json=?, fingerprint_json=?, hints_json=?,"
        " examples_json=?, signature_json=?, times_used=?, last_used_at=? WHERE id=?",
        (p["name"], db.now(), db.dumps(p["columns"]), db.dumps(p["fingerprint"]), db.dumps(p["hints"]),
         db.dumps(p["examples"]), db.dumps(p["signature"]), p["times_used"], p["last_used_at"], p["id"]),
    )


def delete(conn, pid):
    conn.execute("DELETE FROM profiles WHERE id=?", (pid,))


# ── matching ─────────────────────────────────────────────────────────────────

def core(fp):
    n = max(int(fp.get("n_docs", 0)), 1)
    return {t for t, df in fp.get("tokens", {}).items() if df / n >= 0.5}


def match(tokens, structural, profiles):
    D = set(tokens or [])
    cores = {p["id"]: core(p["fingerprint"]) for p in profiles}
    N = len(profiles)
    dfp = Counter(t for c in cores.values() for t in c)

    def idf(t):
        return 1.0 + math.log((1 + N) / (1 + dfp.get(t, 0)))

    scored = []
    for p in profiles:
        C = cores[p["id"]]
        if not C or not D:
            continue
        inter = sum(idf(t) for t in D & C)
        union = sum(idf(t) for t in D | C)
        s = inter / union if union else 0.0
        if s > 0:
            scored.append({"id": p["id"], "name": p["name"], "score": round(s, 3),
                           "struct_ok": p["fingerprint"].get("structural") == structural})
    scored.sort(key=lambda x: -x["score"])
    best = scored[0] if scored else None
    second = scored[1] if len(scored) > 1 else None
    if not best or best["score"] < WEAK:
        return {"decision": "new", "candidates": scored[:5]}
    margin = best["score"] - (second["score"] if second else 0)
    if margin >= MARGIN:
        return {"decision": "propose", "best": best, "strong": best["score"] >= STRONG, "candidates": scored[:5]}
    tied = [c for c in scored if best["score"] - c["score"] < MARGIN]
    struct_hits = [c for c in tied if c["struct_ok"]]
    if len(struct_hits) == 1:
        return {"decision": "propose", "best": struct_hits[0], "strong": False, "candidates": scored[:5]}
    return {"decision": "pick", "candidates": tied[:5]}


# ── learning ─────────────────────────────────────────────────────────────────

def learn(conn, p, doc, table, hints, tokens, structural, signature):
    fp = p["fingerprint"] or {}
    fp.setdefault("tokens", {})
    fp.setdefault("doc_ids", [])
    first_time = doc["id"] not in fp["doc_ids"]

    if first_time:
        toks = fp["tokens"]
        for t in set(tokens or []):
            toks[t] = toks.get(t, 0) + 1
        fp["doc_ids"] = (fp["doc_ids"] + [doc["id"]])[-MAX_FP_DOCS:]
        fp["n_docs"] = len(fp["doc_ids"])
        if len(toks) > MAX_FP_TOKENS:
            fp["tokens"] = dict(sorted(toks.items(), key=lambda kv: -kv[1])[:MAX_FP_TOKENS])
        p["times_used"] = int(p.get("times_used") or 0) + 1
    fp["structural"] = structural or fp.get("structural", {})
    p["fingerprint"] = fp

    p["columns"] = merge_columns(p["columns"], table["columns"], hints, bump=first_time)
    p["hints"] = merge_hints(p["hints"], [h for h in hints if h.get("scope") != "col"],
                             [c["name"] for c in table["columns"]])
    ex = {"doc_id": doc["id"], "columns": [c["name"] for c in table["columns"]],
          "rows": [{k: v for k, v in r.items() if not k.startswith("_")} for r in table["rows"][:3]]}
    p["examples"] = ([ex] + [e for e in p["examples"] if e.get("doc_id") != doc["id"]])[:MAX_EXAMPLES]
    if signature and not p.get("signature"):
        p["signature"] = signature
    p["last_used_at"] = db.now()
    save(conn, p)
    return p


def merge_columns(existing, confirmed, hints, bump=True):
    col_hints = {h["col"]: h["text"] for h in hints if h.get("scope") == "col" and h.get("col") and not h.get("alias")}
    aliases = {}
    for h in hints:
        if h.get("scope") == "col" and h.get("col") and h.get("alias"):
            aliases.setdefault(h["col"].lower(), []).append(h["alias"])
    by_name = {c["name"].lower(): dict(c) for c in existing}
    out = []
    for c in confirmed:
        prev = by_name.pop(c["name"].lower(), None) or {"name": c["name"], "seen": 0, "hint": ""}
        prev["name"] = c["name"]
        prev["kind"] = c.get("kind", prev.get("kind", "row"))
        prev["seen"] = int(prev.get("seen", 0)) + (1 if bump else 0)
        if c["name"] in col_hints:
            prev["hint"] = col_hints[c["name"]]
        al = [a for a in prev.get("aliases", []) if a.lower() != prev["name"].lower()]
        for a in aliases.get(c["name"].lower(), []):
            if a.lower() != prev["name"].lower() and a.lower() not in {x.lower() for x in al}:
                al.append(a)
        prev["aliases"] = al[:10]
        out.append(prev)
    alias_names = {a.lower() for c in out for a in c.get("aliases", [])}
    by_name = {k: v for k, v in by_name.items() if k not in alias_names}
    dropped = {str(h["col"]).lower() for h in hints if h.get("scope") == "col" and h.get("dropped") and h.get("col")}
    for k, c in by_name.items():
        if k not in dropped:
            out.append(c)
    return out


JUNK = ("uses columns", "columns:", "the columns are", "column list", "template uses",
        "following columns", "these columns", "column order is", "headers are")


def useful_hint(text, column_names=()):
    t = (text or "").strip()
    if not t or len(t) > 220:
        return False
    low = t.lower()
    if any(j in low for j in JUNK):
        return False
    hits = sum(1 for c in column_names if c and len(c) > 2 and c.lower() in low)
    return hits < 3


def merge_hints(existing, new, column_names=()):
    seen = {h["text"].strip().lower() for h in existing}
    out = [h for h in existing if useful_hint(h.get("text"), column_names)]
    for h in new:
        key = (h.get("text") or "").strip().lower()
        if key and key not in seen and useful_hint(h.get("text"), column_names):
            out.insert(0, {"text": h["text"].strip(), "added_at": db.now()})
            seen.add(key)
    return out[:MAX_HINTS]


def core_tokens(p, limit=24):
    fp = p.get("fingerprint") or {}
    n = max(int(fp.get("n_docs", 0)), 1)
    items = [(t, df) for t, df in fp.get("tokens", {}).items() if df / n >= 0.5]
    items.sort(key=lambda kv: (-kv[1], kv[0]))
    return [t for t, _ in items[:limit]]
