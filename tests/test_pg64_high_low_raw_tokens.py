"""Regression checks for manually transcribed PG64 page-3 High/Low tokens.

The fixture preserves the rendered source's raw tokens. It does not implement
numeric normalization, infer bid/ask semantics, or establish TOTAL rules.
"""
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "pg64_2026-10-05_page3_og3_call_high_low.json"


def test_page3_high_low_values_remain_assigned_to_their_source_columns():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    assert fixture["source"]["pdf_page"] == 3
    assert fixture["source"]["section_label"] == "OG3 CALL / GOLD OPTIONS / OCT26"
    rows = fixture["rows"]

    assert [row["strike_raw"] for row in rows] == ["4550", "4575", "4600"]
    assert [row["globex_high_low_raw"] for row in rows] == [
        "2.60B/1.70A", "2.20B/1.50A", "1.50/1.30A"
    ]
    assert [row["open_outcry_high_low_raw"] for row in rows] == [
        "2.60B/1.70A", "2.20B/1.50A", "1.80B/1.30A"
    ]


def test_page3_raw_tokens_preserve_blank_markers_signs_and_unchanged_status():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    rows = fixture["rows"]

    assert rows[0]["globex_open_raw"] == "----"
    assert rows[0]["globex_volume_raw"] == "----"
    assert rows[0]["open_interest_change_raw"] == "UNCH"
    assert rows[1]["pt_change_raw"] == "- 0.70"
    assert rows[1]["open_interest_change_raw"] == "+ 1"
    assert rows[2]["pt_change_raw"] == "- 0.60"
    assert rows[2]["open_interest_change_raw"] == "+ 20"
    assert all(row["delta_raw"].startswith(".") for row in rows)
    assert fixture["expected_interpretation"]["production_master_status"] == (
        "BLOCKED_DIAGNOSTIC_ONLY"
    )
