"""Regression tests that PG64 line grouping preserves source token text.

These tests cover text reconstruction only. They do not assign tokens to
semantic columns or claim extraction accuracy for a real CME PDF.
"""
from scripts.parse_pg64 import lines


class FakePage:
    def __init__(self, words):
        self.words = words

    def extract_words(self, **kwargs):
        return list(self.words)


def make_word(text, x0, top=100.0):
    return {"text": text, "x0": x0, "top": top}


def test_line_grouping_preserves_markers_signs_and_bid_ask_suffixes():
    page = FakePage([
        make_word("UNCH", 700),
        make_word("----", 600),
        make_word("- 0.80", 400),
        make_word("2.60B/1.70A", 300),
        make_word(".0187", 500),
        make_word("4550", 50),
    ])

    grouped = lines(page)

    assert len(grouped) == 1
    reconstructed = " ".join(w["text"] for w in grouped[0]["words"])
    assert reconstructed == "4550 2.60B/1.70A - 0.80 .0187 ---- UNCH"


def test_line_grouping_keeps_literal_zero_distinct_from_marker_and_unch():
    page = FakePage([
        make_word("0", 150),
        make_word("----", 250),
        make_word("UNCH", 350),
        make_word("4100", 50),
    ])

    grouped = lines(page)

    assert len(grouped) == 1
    tokens = [w["text"] for w in grouped[0]["words"]]
    assert tokens == ["4100", "0", "----", "UNCH"]
    assert len({tokens[1], tokens[2], tokens[3]}) == 3
