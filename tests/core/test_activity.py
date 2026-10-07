import re

from core import activity


def test_each_line_starts_with_the_time(capsys):
    activity.note("Email from a@b.c: 1 PDF")
    assert re.fullmatch(r"\d\d:\d\d:\d\d  Email from a@b\.c: 1 PDF\n", capsys.readouterr().out)


def test_the_checked_share_rounds_down_and_says_when_nothing_could_be_checked():
    assert activity.checked({"checked": True, "verified": 189, "total": 190}) == "99.4% checked"
    assert activity.checked({"checked": True, "verified": 190, "total": 190}) == "100% checked"
    assert activity.checked({"checked": False, "verified": 0, "total": 0}) == "not checked (scanned)"
    assert (activity.count(1, "row"), activity.count(3, "row")) == ("1 row", "3 rows")
