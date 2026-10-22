from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from create_pg62_cell_reconciliation import build_worksheet


def parsed_fixture():
    row = {
        "contract": "OCT26",
        "source": {"page": 2, "raw_line": "OCT26 4093.60 4099.00 /4080.70"},
    }
    for field in (
        "open", "high", "low", "settlement", "price_change",
        "volume_globex", "volume_pnt_pit", "open_interest", "oi_change",
    ):
        row[field] = {"state": "VALUE", "raw": "4093.60", "value": "4093.60"}
    row["high"]["raw"] = "4099.00"
    row["low"]["raw"] = "4080.70"
    return {
        "dataset": "PG62_GC_FUTURES",
        "trade_date": "2026-10-14",
        "bulletin": {"status": "FINAL"},
        "source": {"sha256": "a" * 64},
        "contracts": [row],
    }


class PG62CellReconciliationWorksheetTests(unittest.TestCase):
    def build(self, parsed=None):
        return build_worksheet(
            parsed or parsed_fixture(),
            source_sha256="a" * 64,
            page_count=8,
            source_url="https://example.invalid/source",
            retrieved_at="2026-10-15T00:00:00Z",
        )

    def test_builds_one_independent_check_per_contract_field(self):
        worksheet = self.build()
        self.assertEqual(len(worksheet["items"]), 10)
        self.assertEqual(
            {item["field"] for item in worksheet["items"]},
            {"contract_code", "open", "high", "low", "settlement", "price_change",
             "volume_globex", "volume_pnt_pit", "open_interest", "oi_change"},
        )
        self.assertTrue(all(item["expected_raw"] == "" for item in worksheet["items"]))
        self.assertTrue(all(item["independently_verified"] is False for item in worksheet["items"]))
        self.assertEqual(worksheet["items"][0]["extracted_raw"], "OCT26")
        self.assertEqual(worksheet["items"][1]["extracted_raw"], "4093.60")
        self.assertEqual(worksheet["pages_reviewed"], [])
        self.assertEqual(worksheet["worksheet_status"], "INCOMPLETE_REVIEW_REQUIRED")

    def test_high_and_low_have_separate_source_tokens(self):
        worksheet = self.build()
        items = {item["field"]: item for item in worksheet["items"]}
        self.assertEqual(items["high"]["extracted_raw"], "4099.00")
        self.assertEqual(items["low"]["extracted_raw"], "4080.70")
        self.assertNotEqual(items["high"]["extracted_raw"], items["low"]["extracted_raw"])

    def test_refuses_hash_mismatch_non_final_and_duplicate_contracts(self):
        with self.assertRaisesRegex(ValueError, "SHA-256 does not match"):
            build_worksheet(parsed_fixture(), source_sha256="b" * 64, page_count=8,
                            source_url="x", retrieved_at="2026-10-15T00:00:00Z")
        non_final = parsed_fixture()
        non_final["bulletin"]["status"] = "PRELIMINARY"
        with self.assertRaisesRegex(ValueError, "requires a FINAL"):
            self.build(non_final)
        duplicate = parsed_fixture()
        duplicate["contracts"].append(copy.deepcopy(duplicate["contracts"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate parsed contract"):
            self.build(duplicate)

    def test_refuses_invalid_page_and_missing_raw_cell(self):
        bad_page = parsed_fixture()
        bad_page["contracts"][0]["source"]["page"] = 9
        with self.assertRaisesRegex(ValueError, "outside the PDF"):
            self.build(bad_page)
        missing = parsed_fixture()
        del missing["contracts"][0]["open"]["raw"]
        with self.assertRaisesRegex(ValueError, "raw token is missing"):
            self.build(missing)


if __name__ == "__main__":
    unittest.main(verbosity=2)
