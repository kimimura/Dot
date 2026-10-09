import config
from core import db
from modules.profiles import hints, repository


def learn(conn, p, doc, table, doc_hints, tokens, structural, signature):
    fp = p["fingerprint"] or {}
    fp.setdefault("tokens", {})
    fp.setdefault("doc_ids", [])
    first_time = doc["id"] not in fp["doc_ids"]

    if first_time:
        toks = fp["tokens"]
        for t in set(tokens or []):
            toks[t] = toks.get(t, 0) + 1
        fp["doc_ids"] = (fp["doc_ids"] + [doc["id"]])[-config.PROFILE_MAX_FP_DOCS:]
        # every confirmed file is counted, as every one added to the word counts; the id list only keeps the latest
        fp["n_docs"] = int(fp.get("n_docs") or 0) + 1
        if len(toks) > config.PROFILE_MAX_FP_TOKENS:
            fp["tokens"] = dict(sorted(toks.items(), key=lambda kv: -kv[1])[:config.PROFILE_MAX_FP_TOKENS])
    fp["structural"] = structural or fp.get("structural", {})
    p["fingerprint"] = fp

    p["columns"] = merge_columns(p["columns"], table["columns"], doc_hints, bump=first_time)
    p["hints"] = hints.merge_hints(p["hints"], [h for h in doc_hints if h.get("scope") != "col"],
                             [c["name"] for c in table["columns"]])
    ex = {"doc_id": doc["id"], "columns": [c["name"] for c in table["columns"]],
          "rows": [{k: v for k, v in r.items() if not k.startswith("_")} for r in table["rows"][:3]]}
    p["examples"] = ([ex] + [e for e in p["examples"] if e.get("doc_id") != doc["id"]])[:config.PROFILE_MAX_EXAMPLES]
    if signature and not p.get("signature"):
        p["signature"] = signature
    repository.save(conn, p, edited=True)
    return p


def merge_columns(existing, confirmed, hints, bump=True):
    col_hints = {h["col"]: h["text"] for h in hints if h.get("scope") == "col" and h.get("col") and not h.get("alias") and not h.get("dropped")}
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
