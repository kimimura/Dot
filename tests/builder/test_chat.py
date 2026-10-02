from modules.builder import chat, chat_prompt, edits
from modules.documents import history


def doc(columns):
    return {"table": {"columns": [{"name": n, "kind": "row"} for n in columns], "rows": [{"_doc": 0, **{n: "" for n in columns}}]},
            "transcript": [{"who": "user", "text": "hello"}], "hints": [{"scope": "col", "col": "Date", "text": "use the {delivery} date"}]}


def test_column_letters_match_the_sheet():
    assert [chat_prompt.letter(i) for i in (0, 1, 2, 5, 6, 25, 26, 27, 51, 52, 701, 702)] == \
        ["A", "B", "C", "F", "G", "Z", "AA", "AB", "AZ", "BA", "ZZ", "AAA"]


def test_dot_is_told_which_letter_is_which_column():
    p = chat_prompt.build(doc(["Invoice No", "Date", "Department", "Art/MCode", "Description", "FOC Ctn", "FOC Pcs"]),
                          "Replace column F and G to Tel and Fax")
    assert "A = Invoice No, B = Date, C = Department, D = Art/MCode, E = Description, F = FOC Ctn, G = FOC Pcs" in p
    assert "Never count columns yourself" in p


def test_dot_is_told_that_revert_means_undo():
    p = chat_prompt.build(doc(["Item"]), "revert please")
    assert '{"op":"undo","steps":N}' in p and '{"op":"undo","steps":1}' in p


def test_the_instructions_build_with_braces_anywhere():
    p = chat_prompt.build(doc(["Qty {pcs}"]), 'set it to {"x": 1}')
    assert 'USER MESSAGE: "set it to {"x": 1}"' in p and "use the {delivery} date" in p


def test_made_up_names_never_become_aliases():
    d = {"hints": []}
    edits.alias_hints(d, [{"renamed": {"old": "Quantity (2)", "new": "Quantity"}},
                          {"renamed": {"old": "Warehouse", "new": "SKU"}}])
    assert [(h["alias"], h["col"]) for h in d["hints"]] == [("Warehouse", "SKU")]


def test_undo_steps_back_one_change_at_a_time():
    d = {"table": "v1", "verification": None, "hints": [], "history": []}
    for v in ("v2", "v3"):
        history.snapshot(d)
        d["table"] = v
    assert history.undo(d) and d["table"] == "v2"
    assert history.undo(d) and d["table"] == "v1"
    assert not history.undo(d) and d["table"] == "v1"


def big_doc(n_rows=278, n_msgs=30):
    cols = [{"name": "PO No.", "kind": "doc"}, {"name": "Item", "kind": "row"}, {"name": "Barcode", "kind": "row"}]
    rows = [{"_doc": i // 50, "PO No.": f"PO-{i // 50}", "Item": f"5430{i:05d}", "Barcode": f"95556846{i:05d}"} for i in range(n_rows)]
    talk = [{"who": "user" if i % 2 == 0 else "bot", "text": f"message {i}"} for i in range(n_msgs)] + [{"who": "user", "text": "now"}]
    return {"table": {"columns": cols, "rows": rows}, "transcript": talk, "hints": [],
            "verification": {"cells": {"199|Barcode": "miss", "200|Item": "elsewhere"}}}


def test_dot_sees_every_row_of_a_long_sheet():
    p = chat_prompt.build(big_doc(), "fix row 278")
    assert "\n278 | 543000277 | 9555684600277" in p and "\n1 | 543000000 |" in p
    assert "DOCUMENT 6: A PO No. = PO-5" in p


def test_dot_remembers_the_whole_conversation():
    p = chat_prompt.build(big_doc(n_msgs=60), "now")
    assert "message 0" in p and "message 59" in p


def test_dot_sees_which_cells_disagree_with_the_pdf():
    p = chat_prompt.build(big_doc(), "x")
    assert "\n200 | 543000199 | 9555684600199 [NOT IN PDF]" in p
    assert "\n201 | 543000200 [ON ANOTHER ROW] |" in p


def test_row_numbers_from_dot_are_the_sheet_s_own():
    assert chat._from_sheet_rows({"op": "set_cell", "row": 200, "col": "Item", "value": "x"})["row"] == 199
    assert chat._from_sheet_rows({"op": "drop_row", "rows": [1, 278]})["rows"] == [0, 277]
    assert chat._from_sheet_rows({"op": "rename_col", "col": "A", "new_name": "B"}) == {"op": "rename_col", "col": "A", "new_name": "B"}
