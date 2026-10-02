import copy

from modules.reading import table_ops


def sheet():
    return {
        "columns": [{"name": "PO No", "kind": "doc"}, {"name": "Item Code", "kind": "row"}, {"name": "Quantity", "kind": "row"},
                    {"name": "Description", "kind": "row"}, {"name": "Note", "kind": "row"}, {"name": "Total", "kind": "row"}],
        "rows": [
            {"_doc": 0, "PO No": "231019", "Item Code": "1160205", "Quantity": "90 PCS", "Description": "Eraser", "Note": "(187130)", "Total": "78.24"},
            {"_doc": 0, "PO No": "231019", "Item Code": "1210307", "Quantity": "48 TUBE", "Description": "Glue", "Note": "", "Total": "399.46"},
            {"_doc": 1, "PO No": "231020", "Item Code": "1210308", "Quantity": "15 TUBE", "Description": "Tape", "Note": "", "Total": "202.07"},
        ],
    }


def apply(*op_list, table=None):
    return table_ops.apply_ops(table or sheet(), list(op_list))


def names(t):
    return [c["name"] for c in t["columns"]]


def row(t, i=0):
    return {c["name"]: t["rows"][i][c["name"]] for c in t["columns"]}


def test_split_into_the_same_name_keeps_the_name():
    t, ch, _ = apply({"op": "split_col", "col": "Quantity", "into": ["Quantity", "UOM"], "sep": " "})
    assert names(t) == ["PO No", "Item Code", "Quantity", "UOM", "Description", "Note", "Total"]
    assert row(t)["Quantity"] == "90" and row(t)["UOM"] == "PCS"
    assert ch == [{"ok": True, "text": 'Split "Quantity" into Quantity, UOM'}]


def test_split_keeping_the_original_needs_a_new_name():
    t, _, _ = apply({"op": "split_col", "col": "Quantity", "into": ["Quantity", "UOM"], "sep": " ", "keep": True})
    assert names(t)[2:5] == ["Quantity", "Quantity (2)", "UOM"]
    assert row(t)["Quantity"] == "90 PCS" and row(t)["Quantity (2)"] == "90"


def test_split_never_overwrites_another_column():
    t, _, _ = apply({"op": "split_col", "col": "Quantity", "into": ["Qty", "Total"], "sep": " "})
    assert row(t)["Total"] == "78.24" and row(t)["Total (2)"] == "PCS"


def test_merge_into_one_of_its_own_names_keeps_the_name():
    t, _, _ = apply({"op": "merge_cols", "cols": ["Description", "Note"], "into": "Description"})
    assert names(t) == ["PO No", "Item Code", "Quantity", "Description", "Total"]
    assert row(t)["Description"] == "Eraser (187130)" and row(t, 1)["Description"] == "Glue"


def test_merge_never_overwrites_another_column():
    t, _, _ = apply({"op": "merge_cols", "cols": ["Description", "Note"], "into": "Total"})
    assert row(t)["Total"] == "78.24" and row(t)["Total (2)"] == "Eraser (187130)"


def test_rename_moves_the_values_and_reports_the_old_name():
    t, ch, _ = apply({"op": "rename_col", "col": "Item Code", "new_name": "Item Code 1"})
    assert row(t)["Item Code 1"] == "1160205" and "Item Code" not in t["rows"][0]
    assert ch[0]["renamed"] == {"old": "Item Code", "new": "Item Code 1"}


def test_rename_to_its_own_name_with_new_casing():
    t, _, _ = apply({"op": "rename_col", "col": "Total", "new_name": "TOTAL"})
    assert names(t)[-1] == "TOTAL"


def test_drop_removes_the_column_everywhere():
    t, _, _ = apply({"op": "drop_col", "col": "Note"})
    assert "Note" not in names(t) and all("Note" not in r for r in t["rows"])


def test_the_original_table_is_never_changed():
    before = sheet()
    original = copy.deepcopy(before)
    table_ops.apply_ops(before, [{"op": "drop_col", "col": "Note"}, {"op": "rename_col", "col": "Total", "new_name": "Amount"}])
    assert before == original


def test_add_column_with_one_value_per_row():
    t, _, edited = apply({"op": "add_col", "name": "Email", "values": ["a@x.my", "b@x.my", "c@x.my"]})
    assert names(t)[-1] == "Email" and [r["Email"] for r in t["rows"]] == ["a@x.my", "b@x.my", "c@x.my"]
    assert "0|Email" in edited


def test_set_column_with_the_wrong_count_changes_nothing():
    t, ch, _ = apply({"op": "set_col", "col": "Total", "values": ["1", "2", "3", "4"]})
    assert ch[0]["ok"] is False and "needs 3 values (one per row) or 2 (one per document), got 4" in ch[0]["text"]
    assert t == sheet()


def test_one_value_per_document_fills_each_document():
    t, ch, _ = apply({"op": "add_col", "name": "Address Code", "values": ["10022 BK", "10067 JM"]})
    assert [r["Address Code"] for r in t["rows"]] == ["10022 BK", "10022 BK", "10067 JM"]
    assert t["columns"][1] == {"name": "Address Code", "kind": "doc"} and ch[0]["ok"]


def test_add_column_with_too_few_values_is_refused_not_left_blank():
    t, ch, _ = apply({"op": "add_col", "name": "Code", "values": ["a"] * 40})
    assert ch[0]["ok"] is False and "Code" not in names(t)


def test_part_of_a_column_is_copied_into_a_new_one_for_every_row():
    table = sheet()
    for r, a in zip(table["rows"], ["10022 BK ECONSAVE CASH & CARRY (BK)", "10022 BK ECONSAVE CASH & CARRY (BK)", "10128 GBK Econsave (EC)"]):
        r["Address"] = a
    table["columns"].insert(1, {"name": "Address", "kind": "doc"})
    t, ch, _ = apply({"op": "extract_col", "col": "Address", "into": "Address Code", "pattern": r"^(\d+ \S+)"}, table=table)
    assert [r["Address Code"] for r in t["rows"]] == ["10022 BK", "10022 BK", "10128 GBK"]
    assert ch[0]["text"] == 'Filled "Address Code" from "Address" (3 of 3 rows)'


def test_an_empty_column_with_that_name_is_filled_instead_of_duplicated():
    table = sheet()
    table["columns"].append({"name": "Address Code", "kind": "doc"})
    for r in table["rows"]:
        r["Address Code"] = ""
    t, _, _ = apply({"op": "extract_col", "col": "Item Code", "into": "Address Code", "pattern": r"^\d{3}"}, table=table)
    assert names(t).count("Address Code") == 1 and t["rows"][0]["Address Code"] == "116"


def test_a_pattern_that_matches_nothing_is_refused():
    t, ch, _ = apply({"op": "extract_col", "col": "Description", "into": "X", "pattern": r"^\d{9}"})
    assert ch[0]["ok"] is False and "X" not in names(t)


def test_set_cell_on_a_document_field_updates_that_whole_document():
    t, _, _ = apply({"op": "set_cell", "row": 0, "col": "PO No", "value": "231019A"})
    assert [r["PO No"] for r in t["rows"]] == ["231019A", "231019A", "231020"]


def test_reorder_puts_named_columns_first():
    t, _, _ = apply({"op": "reorder_cols", "order": ["Total", "Item Code"]})
    assert names(t) == ["Total", "Item Code", "PO No", "Quantity", "Description", "Note"]


def test_transform_dates_and_numbers():
    table = {"columns": [{"name": "Date", "kind": "row"}, {"name": "Amount", "kind": "row"}],
             "rows": [{"_doc": 0, "Date": "12/09/2026", "Amount": "RM 1,250.00"}, {"_doc": 0, "Date": "soon", "Amount": "7"}]}
    t, ch, _ = apply({"op": "transform_col", "col": "Date", "kind": "date"}, {"op": "transform_col", "col": "Amount", "kind": "currency"},
                     table=table)
    assert [r["Date"] for r in t["rows"]] == ["2026-09-12", "soon"]
    assert [r["Amount"] for r in t["rows"]] == ["1,250.00", "7.00"]
    assert "1 values left as-is" in ch[0]["text"]


def test_fill_down_only_fills_blanks():
    t, ch, _ = apply({"op": "fill_down", "col": "Note"})
    assert [r["Note"] for r in t["rows"]] == ["(187130)"] * 3 and ch[0]["text"] == 'Filled 2 blank cells in "Note"'


def test_dropping_every_row_leaves_one_empty_row():
    t, _, _ = apply({"op": "drop_row", "rows": [0, 1, 2]})
    assert len(t["rows"]) == 1 and not any(v for k, v in t["rows"][0].items() if k != "_doc")


def test_unknown_columns_and_ops_are_reported_and_the_rest_still_applies():
    t, ch, _ = apply({"op": "drop_col", "col": "Nope"}, {"op": "teleport"}, {"op": "drop_col", "col": "Note"})
    assert [c["ok"] for c in ch] == [False, False, True]
    assert ch[0]["text"] == 'No column called "Nope"'
    assert "Note" not in names(t)
