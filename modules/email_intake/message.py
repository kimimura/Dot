import base64
import html
import re
from collections import Counter

import config
from core import sheets


def _safe(name):
    return re.sub(r'[\\/:*?"<>|\[\]]+', "-", name).strip() or config.EMAIL_UNIDENTIFIED


def _label(doc):
    if doc["stage"] == "converted":
        return doc.get("profile_name") or config.EMAIL_UNIDENTIFIED
    return config.EMAIL_UNREADABLE if doc["stage"] == "failed" else config.EMAIL_UNFINISHED


def _file_names(docs, labels, stamp):
    # files of one format from one email share the arrival time, so they are numbered when there is more than one
    done = [d["stage"] == "converted" and d.get("table") for d in docs]
    totals, seen, names = Counter(l for l, ok in zip(labels, done) if ok), Counter(), []
    for label, ok in zip(labels, done):
        if not ok:
            names.append(None)
            continue
        seen[label] += 1
        base = config.EMAIL_FILE_NAME.format(format=_safe(label), stamp=stamp)
        names.append(f"{base}_{seen[label]}.xlsx" if totals[label] > 1 else f"{base}.xlsx")
    return names


def build(docs, stamp, sender):
    labels = [_label(d) for d in docs]
    names = _file_names(docs, labels, stamp)
    subject = config.EMAIL_SUBJECT.format(n=len(docs), s="" if len(docs) == 1 else "s")
    parts, attachments = [f"<p><b>{html.escape(subject)}</b></p>"], []
    for d, label, name in zip(docs, labels, names):
        line = f"<p><b>{html.escape(d['filename'])} – {html.escape(label)}</b>"
        if name:
            rows = len(d["table"]["rows"])
            line += "<br>" + html.escape(config.EMAIL_FILE_LINE.format(rows=rows, s="" if rows == 1 else "s", file=name))
            data = sheets.xlsx_bytes(d["table"], _safe(label)).getvalue()
            attachments.append({"Name": name, "ContentBytes": base64.b64encode(data).decode("ascii")})
        parts.append(line + "</p>")
    return {"subject": subject, "body": "".join(parts), "attachments": attachments, "to": sender,
            "delivered_count": len(attachments), "held_count": 0, "failed_count": len(docs) - len(attachments)}
