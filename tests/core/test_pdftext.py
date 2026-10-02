import pdfgen
from core import pdftext


def test_words_printed_apart_without_a_space_get_one():
    # "Shah" is 23.35pt wide in 10pt Helvetica; "Alam" starts 1.2pt after it, too close for the PDF library to add a space
    pdf = pdfgen.build([[pdfgen.text(50, 700, "Shah"), pdfgen.text(74.55, 700, "Alam"), pdfgen.text(50, 680, "Selangor 40460")]])
    lines = pdftext.page_texts(pdf)[0].splitlines()
    assert lines[0] == "Shah Alam"
    assert lines[1] == "Selangor 40460"


def test_letters_of_one_word_are_never_split():
    pdf = pdfgen.build([[pdfgen.text(50, 700, "Faber-Castell Dust-Free Eraser (187130) PP001-00 2's/pkt", 9)]])
    assert pdftext.page_texts(pdf)[0].strip() == "Faber-Castell Dust-Free Eraser (187130) PP001-00 2\u2019s/pkt"
