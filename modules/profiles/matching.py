import math
from collections import Counter

import config


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
    if not best or best["score"] < config.MATCH_WEAK:
        return {"decision": "new", "candidates": scored[:5]}
    margin = best["score"] - (second["score"] if second else 0)
    if margin >= config.MATCH_MARGIN:
        return {"decision": "propose", "best": best, "strong": best["score"] >= config.MATCH_STRONG, "candidates": scored[:5]}
    tied = [c for c in scored if best["score"] - c["score"] < config.MATCH_MARGIN]
    struct_hits = [c for c in tied if c["struct_ok"]]
    if len(struct_hits) == 1:
        return {"decision": "propose", "best": struct_hits[0], "strong": False, "candidates": scored[:5]}
    return {"decision": "pick", "candidates": tied[:5]}


def core_tokens(p, limit=config.PROFILE_CORE_TOKENS_SHOWN):
    fp = p.get("fingerprint") or {}
    n = max(int(fp.get("n_docs", 0)), 1)
    items = [(t, df) for t, df in fp.get("tokens", {}).items() if df / n >= 0.5]
    items.sort(key=lambda kv: (-kv[1], kv[0]))
    return [t for t, _ in items[:limit]]
