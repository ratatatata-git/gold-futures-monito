"""Tests for PG64 PDF word grouping by vertical position and column order.

These tests exercise the parser's line-grouping algorithm using coordinate
samples. They do not claim end-to-end extraction accuracy against CME PDFs.
"""
from scripts.parse_pg64 import lines


class FakePage:
    def __init__(self, words):
        self._words = words

    def extract_words(self, **kwargs):
        assert kwargs == {
            "x_tolerance": 1,
            "y_tolerance": 2,
            "keep_blank_chars": False,
        }
        return list(self._words)


def word(text, x0, top):
    return {"text": text, "x0": x0, "top": top}


def test_lines_sorts_words_left_to_right_even_when_input_is_unsorted():
    page = FakePage([
        word("10", 230, 100.1),
        word("4100", 50, 100.0),
        word("121.20", 150, 100.2),
    ])

    result = lines(page)

    assert len(result) == 1
    assert [item["text"] for item in result[0]["words"]] == [
        "4100", "121.20", "10"
    ]


def test_lines_groups_small_vertical_jitter_but_keeps_separate_rows():
    page = FakePage([
        word("4375", 50, 120.0),
        word("23.20", 150, 121.8),
        word("5", 230, 120.9),
        word("4400", 50, 124.0),
        word("20.10", 150, 124.2),
    ])

    result = lines(page)

    assert len(result) == 2
    assert [
        [item["text"] for item in row["words"]]
        for row in result
    ] == [
        ["4375", "23.20", "5"],
        ["4400", "20.10"],
    ]


def test_lines_does_not_merge_rows_outside_vertical_tolerance():
    page = FakePage([
        word("4500", 50, 200.0),
        word("9.20", 150, 203.0),
    ])

    result = lines(page)

    assert len(result) == 2
