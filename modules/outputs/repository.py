from core import db


def get(conn, did, version):
    r = conn.execute("SELECT json FROM outputs WHERE document_id=? AND version=?", (did, version)).fetchone()
    return db.loads(r["json"], None) if r else None


def save_current(conn, did, chain, process_date, data):
    conn.execute("DELETE FROM outputs WHERE document_id=? AND version='current'", (did,))
    conn.execute("INSERT INTO outputs(document_id,version,chain,process_date,json) VALUES(?,'current',?,?,?)",
                 (did, chain, process_date, db.dumps(data)))


def keep_sent(conn, did, chain, process_date, data):
    # what went out is written once and never changed afterwards
    conn.execute("INSERT INTO outputs(document_id,version,chain,process_date,json)"
                 " SELECT ?,'sent',?,?,? WHERE NOT EXISTS (SELECT 1 FROM outputs WHERE document_id=? AND version='sent')",
                 (did, chain, process_date, db.dumps(data), did))


def clear_current(conn, did):
    conn.execute("DELETE FROM outputs WHERE document_id=? AND version='current'", (did,))
