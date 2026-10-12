"""Additional PG64 fail-closed edge cases and fixture provenance checks."""

import json
from pathlib import Path

import pytest

from scripts.pg64_reconciliation import parse_integer_token, reconcile_integer_total


ROOT = Path(__file__).resolve().parent.parent
FIXTURES = [
    ROOT / "tests/fixtures/pg64_2026-10-05_page2_og5_call_total.json",
    ROOT / "tests/fixtures/pg64_2026-10-05_page3_og3_call_high_low.json",
]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0", 0),
        ("+0", 0),
        ("-0", 0),
        (" + 12 ", 12),
        ("- 12", -12),
        ("1,000", None),
        ("1.0", None),
        ("1e3", None),
        ("--", None),
        ("N/A", None),
        ("NEW", None),
        ("UNCH", None),
        ("2.60B/1.70A", None),
        ("", None),
        ("   ", None),
        (None, None),
    ],
)
def test_integer_parser_accepts_only_explicit_integer_tokens(raw, expected):
    assert parse_integer_token(raw) == expected


@pytest.mark.parametrize("fixture_path", FIXTURES, ids=lambda p: p.name)
def test_manual_fixture_has_explicit_provenance_and_keeps_diagnostic_gate(fixture_path):
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    source = fixture["source"]

    assert fixture["fixture_schema"] == "pg64.manual-source-fixture.v1"
    assert source["repository_path"] == "data/cme-pg64/PG64_2026-10-05.pdf"
    assert source["trade_date"] == "2026-10-05"
    assert source["bulletin_number"] == "191"
    assert source["bulletin_status"] in {"PRELIMINARY", "FINAL"}
    assert source["pdf_page"] > 0
    assert source["section_label"]
    assert fixture.get("expected_reconciliation", fixture.get("expected_interpretation"))[
        "production_master_status"
    ] == "BLOCKED_DIAGNOSTIC_ONLY"


def test_reconciliation_does_not_sum_when_any_row_is_unparseable():
    result = reconcile_integer_total(["4", "NEW", "6"], "10")
    assert result == {
        "status": "UNRESOLVED",
        "row_sum": None,
        "printed_total": 10,
        "unresolved_row_indices": [1],
    }


def test_reconciliation_reports_mismatch_without_silently_correcting_total():
    result = reconcile_integer_total(["4", "6"], "11")
    assert result["status"] == "MISMATCH"
    assert result["row_sum"] == 10
    assert result["printed_total"] == 11
