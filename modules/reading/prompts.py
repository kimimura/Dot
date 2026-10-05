import json


DOC_KINDS = "invoice|purchase_order|receipt|statement|delivery_note|quotation|form|report|letter|other"
SCHEMA_TEXT = f"""Return ONLY a JSON object with this exact shape:
{{
  "signature": {{"title": "document title or type as printed", "issuer": "organisation that produced it", "doc_kind": "{DOC_KINDS}"}},
  "documents": [
    {{
      "document_fields": {{"Field Name": "value as printed", "...": "..."}},
      "row_columns": ["Column A", "Column B", "..."],
      "rows": [["value for Column A", "value for Column B", "..."], ["..."]]
    }}
  ],
  "extra_fields": {{}}
}}
Rules:
- One entry in "documents" per distinct document inside the file (most files contain exactly one).
- "document_fields" are values that appear once per document: reference numbers, dates, names, addresses, totals, terms.
- "rows" are the repeating line items (products, transactions, entries). "row_columns" lists their column names in the order printed, and each row is a list of values in exactly that order. If there are no repeating items, use [] for both.
- Include EVERY line item on EVERY page, in page order. Never summarise, sample or stop early; long lists are expected.
- Copy values exactly as printed, including number formatting. Use "" when a value is absent. Every value is a string.
- Column and field names: short, Title Case, unique, no trailing colons.
"""
SCHEMA_ALL_IN_SHEET = SCHEMA_TEXT.replace('  ],\n  "extra_fields": {}\n}', "  ]\n}")
EVERY_FIELD = ("Extract every field printed in the document and every repeating row, including contact details "
               "(phone, fax, e-mail), reference numbers and notes; the user removes what they don't need.")
FRESH_PROMPT = f"""You are reading a PDF and turning it into a spreadsheet. {EVERY_FIELD} Do not invent values.

""" + SCHEMA_ALL_IN_SHEET


def profile_prompt(profile, hints, fresh=False):
    doc_cols = [c for c in profile["columns"] if c.get("kind") == "doc"]
    row_cols = [c for c in profile["columns"] if c.get("kind") != "doc"]

    def fmt(cols):
        return "\n".join(f'  - "{c["name"]}"' + (f' — {c["hint"]}' if c.get("hint") else "") for c in cols) or "  (none)"

    columns_rule = (f"Use the columns below with these exact names, and add any other field you find as a new column. {EVERY_FIELD}"
                    if fresh else 'Produce exactly the columns below, using these exact names. Use "" for any column that is absent in this document. Do not add other columns to the table.')
    lines = [
        f'You are reading a PDF in a known format called "{profile["name"]}". {columns_rule}',
        "", "Document-level fields (once per document):", fmt(doc_cols),
        "", "Row-level columns (one per repeating line item):", fmt(row_cols),
    ]
    rules = [h["text"] for h in profile.get("hints", [])] + [h["text"] for h in hints if h.get("scope") != "col"]
    if rules:
        lines += ["", "Rules learned from previous documents of this format:"] + [f"  - {r}" for r in rules]
    ex = (profile.get("examples") or [None])[0]
    rcols = [c["name"] for c in row_cols]
    if ex and ex.get("rows") and rcols:
        sample = {"row_columns": rcols, "rows": [[r.get(c, "") for c in rcols] for r in ex["rows"][:2]]}
        lines += ["", "Example rows from a previous document of this format:", json.dumps(sample, ensure_ascii=False)]
    if fresh:
        lines += ["", SCHEMA_ALL_IN_SHEET]
    else:
        lines += ["", 'If you notice useful fields that are NOT in the list, put them in "extra_fields" (name → value) instead of the table.', "", SCHEMA_TEXT]
    return "\n".join(lines)


def build_prompt(profile=None, hints=None, instruction=None, fresh=False):
    p = profile_prompt(profile, hints or [], fresh) if profile else FRESH_PROMPT
    if hints and not profile:
        p += "\nAdditional rules from the user:\n" + "\n".join(f"  - {h['text']}" for h in hints if h.get("text"))
    if instruction:
        p += f"\n\nThe user asked for this change to the extraction — follow it precisely:\n{instruction}\n"
    return p
