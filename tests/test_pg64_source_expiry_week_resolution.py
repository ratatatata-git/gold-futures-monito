"""Focused tests for weekly expiry resolution using dates printed in a bulletin.

These tests exercise the source-evidence helper only. They do not validate
PDF extraction of the expiry table or certify weekly product resolution
end-to-end.
"""
import pytest

from scripts.parse_pg64 import ProductResolver


def resolve(dates, trade_date="2026-09-29", weekday="MON"):
    return ProductResolver._week_from_source_expiry_date(
        "GMW",
        weekday,
        {"__YEAR__": ["2026"], "GMW": dates},
        trade_date,
    )


def test_skips_expiry_before_bulletin_trade_date_and_uses_next_printed_date():
    assert resolve(["09/28", "10/05"]) == "1"


def test_week_number_tracks_the_calendar_occurrence_of_the_expiry_date():
    assert resolve(["10/05"]) == "1"
    assert resolve(["10/12"]) == "2"
    assert resolve(["10/26"]) == "4"


@pytest.mark.parametrize(
    ("dates", "trade_date", "weekday"),
    [
        ([], "2026-09-29", "MON"),
        (["10/05"], "not-a-date", "MON"),
        (["10/05"], "2026-09-29", "FUNDAY"),
        (["10/06"], "2026-09-29", "MON"),
        (["not-a-date"], "2026-09-29", "MON"),
    ],
)
def test_missing_malformed_or_weekday_mismatched_source_evidence_fails_closed(
    dates, trade_date, weekday
):
    assert resolve(dates, trade_date, weekday) == ""


def test_ambiguous_printed_year_fails_closed():
    assert ProductResolver._week_from_source_expiry_date(
        "GMW",
        "MON",
        {"__YEAR__": ["2026", "2027"], "GMW": ["10/05"]},
        "2026-09-29",
    ) == ""


def test_invalid_calendar_date_is_ignored_without_guessing():
    assert resolve(["02/30", "10/05"]) == "1"
