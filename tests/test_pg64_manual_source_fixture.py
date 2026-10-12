"""Regression checks for the manually transcribed PG64 page-2 example.

These checks lock source-derived fixture values; they do not implement the
production parser or establish general aggregation semantics for other groups.
"""
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "pg64_2026-10-05_page2_og5_call_total.json"


def test_manual_pg64_fixture_keeps_source_identity_and_raw_tokens():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    assert fixture["fixture_schema"] == "pg64.manual-source-fixture.v1"
    assert fixture["source"]["pdf_page"] == 2
    assert fixture["source"]["section_label"] == "OG5 CALL / GOLD OPTIONS / OCT26"
    assert fixture["source"]["bulletin_status"] == "PRELIMINARY"
    assert (
        fixture["expected_reconciliation"]["production_master_status"]
        == "BLOCKED_DIAGNOSTIC_ONLY"
    )

    rows = fixture["rows"]
    assert [row["strike"] for row in rows] == ["4100", "4375", "4500", "4525"]
    assert [row["delta_raw"] for row in rows] == [".6111", ".1820", ".0904", ".0785"]
    assert [row["settlement_price_raw"] for row in rows] == [
        "121.20", "23.20", "10.70", "9.20"
    ]
    assert all("globex_volume_raw" in row and "open_interest_raw" in row for row in rows)


def test_manual_pg64_page2_total_example_reconciles_only_declared_measures():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    rows = fixture["rows"]
    total = fixture["printed_total"]
    expected = fixture["expected_reconciliation"]

    volume_sum = sum(int(row["globex_volume_raw"]) for row in rows)
    oi_sum = sum(int(row["open_interest_raw"]) for row in rows)

    assert volume_sum == int(total["globex_volume_raw"]) == 10
    assert oi_sum == int(total["open_interest_raw"]) == 10
    assert expected["globex_volume"]["status"] == "MATCH"
    assert expected["open_interest"]["status"] == "MATCH_FOR_THIS_FIXTURE_ONLY"
    assert expected["open_interest_change"]["status"] == "MATCH_FOR_THIS_FIXTURE_ONLY"
    assert fixture["source"]["scope_note"].endswith("not a general TOTAL rule.")
