#!/usr/bin/env python3
"""Offline tests for CFTC Gold COT ingestion and idempotent history updates."""

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import fetch_cot_gold  # noqa: E402


def fixture_row(date="2026-09-29", long_value="12345"):
    return {
        "report_date_as_yyyy_mm_dd": date,
        "cftc_contract_market_code": "088691",
        "market_and_exchange_names": "GOLD - COMMODITY EXCHANGE INC.",
        "open_interest_all": "450000",
        "m_money_positions_long_all": long_value,
        "m_money_positions_short_all": "6789",
    }


def payload(*rows):
    return json.dumps(list(rows), separators=(",", ":")).encode("utf-8")


class CotGoldIngestionTests(unittest.TestCase):
    def test_rejects_empty_or_unexpected_market_data(self):
        with self.assertRaisesRegex(ValueError, "no rows"):
            fetch_cot_gold.validate_records(b"[]")

        wrong_market = fixture_row()
        wrong_market["market_and_exchange_names"] = "SILVER - COMMODITY EXCHANGE INC."
        with self.assertRaisesRegex(ValueError, "Unexpected market name"):
            fetch_cot_gold.validate_records(payload(wrong_market))

    def test_rejects_duplicate_keys_in_one_response(self):
        row = fixture_row()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            fetch_cot_gold.validate_records(payload(row, row))

    def test_reingestion_is_idempotent_and_preserves_raw_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            history_path = root / "history.json"
            raw_dir = root / "raw"
            source = payload(fixture_row())

            first = fetch_cot_gold.ingest(
                source, "2026-10-16T00:00:00+00:00", history_path, raw_dir
            )
            second = fetch_cot_gold.ingest(
                source, "2026-10-17T00:00:00+00:00", history_path, raw_dir
            )
            history = json.loads(history_path.read_text(encoding="utf-8"))

            self.assertEqual(first["rows_added"], 1)
            self.assertEqual(second["rows_added"], 0)
            self.assertEqual(second["rows_revised"], 0)
            self.assertEqual(len(history["records"]), 1)
            self.assertEqual(len(history["snapshots"]), 2)
            self.assertEqual(first["sha256"], hashlib.sha256(source).hexdigest())
            self.assertEqual(len(list(raw_dir.glob("*.json"))), 1)
            self.assertEqual(history["records"][0]["m_money_positions_long_all"], "12345")

    def test_official_correction_updates_history_but_keeps_prior_raw_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            history_path = root / "history.json"
            raw_dir = root / "raw"

            first_payload = payload(fixture_row(long_value="12345"))
            corrected_payload = payload(fixture_row(long_value="12399"))
            fetch_cot_gold.ingest(first_payload, "2026-10-16T00:00:00+00:00", history_path, raw_dir)
            result = fetch_cot_gold.ingest(
                corrected_payload, "2026-10-17T00:00:00+00:00", history_path, raw_dir
            )
            history = json.loads(history_path.read_text(encoding="utf-8"))

            self.assertEqual(result["rows_added"], 0)
            self.assertEqual(result["rows_revised"], 1)
            self.assertEqual(len(history["records"]), 1)
            self.assertEqual(history["records"][0]["m_money_positions_long_all"], "12399")
            self.assertEqual(len(list(raw_dir.glob("*.json"))), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
