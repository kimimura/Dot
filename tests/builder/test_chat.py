from modules.builder import chat, chat_prompt, edits
from modules.documents import history
from modules.profiles import learning
from modules.reading import table_ops


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


def test_dot_writes_column_hints_as_extract_instructions():
    p = chat_prompt.build(doc(["Qty"]), "only keep the number")
    assert 'A column hint (scope col) always starts with "Extract"' in p
    assert '"text": "Extract ... (what to take for that column, and from where)"' in p


def test_dot_sees_the_changes_it_already_made():
    d = doc(["Item"])
    d["transcript"] = [{"who": "user", "text": "rename Qty"}, {"who": "sys", "text": "", "changes": [{"ok": True, "text": 'Renamed "Qty" to "Item"'}]},
                       {"who": "user", "text": "now"}]
    assert '(Changes applied: Renamed "Qty" to "Item")' in chat_prompt.build(d, "now")


LETTERED = ["Invoice No", "Date", "Customer", "Total", "Item", "ID"]


def test_column_letters_in_an_edit_become_the_columns_the_user_saw():
    def turn(o):
        return chat._from_sheet_letters(o, LETTERED)
    assert turn({"op": "rename_col", "col": "D", "new_name": "Amount"}) == {"op": "rename_col", "col": "Total", "new_name": "Amount"}
    assert turn({"op": "merge_cols", "cols": ["b", "C"], "into": "AB"})["cols"] == ["Date", "Customer"]
    assert turn({"op": "merge_cols", "cols": ["B", "C"], "into": "AB"})["into"] == "AB"
    assert turn({"op": "reorder_cols", "order": ["E", "A"]})["order"] == ["Item", "Invoice No"]
    assert turn({"op": "add_row", "values": {"A": "INV-1"}})["values"] == {"Invoice No": "INV-1"}
    assert turn({"op": "drop_col", "col": "Z"})["col"] == "Z"
    assert chat._from_sheet_letters({"op": "drop_col", "col": "B"}, ["Item", "Qty", "B"])["col"] == "B"
    assert turn({"op": "drop_col", "col": "Customer"})["col"] == "Customer"


def test_a_place_given_by_letter_becomes_the_column_standing_there():
    def turn(o):
        return chat._from_sheet_letters(o, LETTERED)
    assert turn({"op": "add_col", "name": "Store Code", "at": "B"})["at"] == "Date"
    assert turn({"op": "move_col", "col": "F", "to": "a"}) == {"op": "move_col", "col": "ID", "to": "Invoice No"}
    assert turn({"op": "add_col", "name": "Note", "after": "C"})["after"] == "Customer"
    assert turn({"op": "add_col", "name": "Note", "at": "G"}) == {"op": "add_col", "name": "Note", "after": "ID"}


def test_dot_is_told_to_pass_letters_through():
    p = chat_prompt.build(doc(["Item"]), "drop column A")
    assert 'put that letter exactly as the user wrote it' in p and "use the column's name in ops" not in p


def test_dot_is_pointed_at_the_right_edit_instead_of_typing_values():
    p = chat_prompt.build(doc(["Qty"]), "these values are wrong")
    assert '{"op":"reread_cols","cols":["K","L"]}' in p
    assert "Never type out values for more than 20 rows yourself" in p and 'mean reread_cols' in p
    assert '"Move X into ROWS"' in p and "mean set_col_kind" in p
    assert "Keep values exactly as printed. Use transform_col only when the user asks to reformat" in p


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
    assert "\n200 | 543000199 | 9555684600199 [DOESN'T MATCH PDF]" in p
    assert "\n201 | 543000200 [ON ANOTHER ROW] |" in p


def test_row_numbers_from_dot_are_the_sheet_s_own():
    assert chat._from_sheet_rows({"op": "set_cell", "row": 200, "col": "Item", "value": "x"})["row"] == 199
    assert chat._from_sheet_rows({"op": "drop_row", "rows": [1, 278]})["rows"] == [0, 277]
    assert chat._from_sheet_rows({"op": "rename_col", "col": "A", "new_name": "B"}) == {"op": "rename_col", "col": "A", "new_name": "B"}


def item_codes():
    return {"columns": [{"name": "Item Code", "kind": "row"}, {"name": "Qty", "kind": "row"}],
            "rows": [{"_doc": 0, "Item Code": "FC-100028295", "Qty": "6"}, {"_doc": 0, "Item Code": "FC-311802", "Qty": "2"}]}


CLEAN_COPY = [{"op": "extract_col", "col": "Item Code", "into": "Item Code 2", "pattern": r"\d+"},
              {"op": "drop_col", "col": "Item Code"},
              {"op": "rename_col", "col": "Item Code 2", "new_name": "Item Code"}]


def test_a_cleaned_copy_renamed_back_keeps_the_column_and_saves_the_rule():
    hints = [{"scope": "col", "col": "Item Code", "text": 'Do not extract "Item Code"', "dropped": True}]
    table, changes, _ = table_ops.apply_ops(item_codes(), CLEAN_COPY, set(), typed_by_model=True)
    assert [r["Item Code"] for r in table["rows"]] == ["100028295", "311802"]
    settled = edits.settle_hints(hints, CLEAN_COPY, changes, table)
    assert not any(h.get("dropped") for h in settled)
    assert edits.column_notes(settled)["Item Code"] == r'Extract only the part of "Item Code" that matches the pattern \d+'


def test_a_column_that_already_has_a_rule_keeps_the_user_s_own_words():
    own = {"scope": "col", "col": "Item Code", "text": "Extract the digits after FC-"}
    table, changes, _ = table_ops.apply_ops(item_codes(), CLEAN_COPY, set(), typed_by_model=True)
    assert edits.column_notes(edits.settle_hints([own], CLEAN_COPY, changes, table))["Item Code"] == own["text"]


def test_a_column_really_dropped_stays_out_of_the_next_read():
    ops = [{"op": "drop_col", "col": "Qty"}]
    hints = [{"scope": "col", "col": "Qty", "text": 'Do not extract "Qty"', "dropped": True}]
    table, changes, _ = table_ops.apply_ops(item_codes(), ops, set(), typed_by_model=True)
    assert edits.settle_hints(hints, ops, changes, table) == hints


def test_a_working_name_for_a_cleaned_copy_is_never_saved_as_a_printed_header():
    d = {"hints": []}
    _, changes, _ = table_ops.apply_ops(item_codes(), CLEAN_COPY, set(), typed_by_model=True)
    edits.alias_hints(d, changes)
    assert d["hints"] == []


def test_the_saved_format_keeps_the_rule_not_the_drop_of_a_column_that_came_back():
    hints = [{"scope": "col", "col": "Item Code", "text": "Extract only the digits after FC-"},
             {"scope": "col", "col": "Item Code", "text": 'Do not extract "Item Code"', "dropped": True}]
    cols = learning.merge_columns([], [{"name": "Item Code", "kind": "row"}], hints)
    assert cols[0]["hint"] == "Extract only the digits after FC-"
