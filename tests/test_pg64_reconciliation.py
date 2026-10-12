"""Unit tests for fail-closed PG64 integer-token reconciliation.

These tests exercise an isolated helper only. They do not establish which PG64
columns have additive TOTAL semantics and do not enable production output.
"""
from scripts.pg64_reconciliation import parse_integer_token, reconcile_integer_total


def test_explicit_integer_tokens_preserve_zero_and_signed_values():
    assert parse_integer_token("0") == 0
    assert parse_integer_token("10") == 10
    assert parse_integer_token("+ 10") == 10
    assert parse_integer_token("- 2") == -2


def test_blank_marker_and_ambiguous_tokens_are_not_coerced_to_zero():
    assert parse_integer_token(None) is None
    assert parse_integer_token("") is None
    assert parse_integer_token("   ") is None
    assert parse_integer_token("----") is None
    assert parse_integer_token("UNCH") is None
    assert parse_integer_token("1O") is None
    assert parse_integer_token("2.5") is None


def test_reconciliation_reports_match_only_for_explicit_numeric_values():
    result = reconcile_integer_total(["1", "5", "3", "1"], "10")
    assert result == {
        "status": "MATCH",
        "row_sum": 10,
        "printed_total": 10,
        "unresolved_row_indices": [],
    }


def test_reconciliation_detects_deliberately_mismatched_total():
    result = reconcile_integer_total(["1", "5", "3", "1"], "11")
    assert result["status"] == "MISMATCH"
    assert result["row_sum"] == 10
    assert result["printed_total"] == 11


def test_reconciliation_fails_closed_if_any_row_or_total_is_unresolved():
    row_result = reconcile_integer_total(["1", "----", "3"], "4")
    assert row_result["status"] == "UNRESOLVED"
    assert row_result["row_sum"] is None
    assert row_result["unresolved_row_indices"] == [1]

    total_result = reconcile_integer_total(["1", "2"], "UNCH")
    assert total_result["status"] == "UNRESOLVED"
    assert total_result["row_sum"] is None
