import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import validate_pdf_reconciliation as validator  # noqa: E402


def valid_report():
    return {
        "schema_version": 1,
        "document": {
            "bulletin_type": "PG62",
            "bulletin_date": "2026-10-15",
            "edition_status": "FINAL",
            "sha256": "a" * 64,
            "page_count": 2,
            "source_url": "https://example.invalid/official-source",
            "retrieved_at": "2026-10-16T10:00:00Z"
        },
        "review": {
            "reviewer": "independent reviewer",
            "reviewed_at": "2026-10-16T12:00:00Z",
            "method": "independent_manual_pdf"
        },
        "pages_reviewed": [1, 2],
        "items": [
            {
                "check_id": "pg62-p1-settlement",
                "page_number": 1,
                "locator": "page 1 / table A / GC row / settlement cell",
                "field": "settlement_raw",
                "expected_raw": "2,345.6",
                "extracted_raw": "2,345.6",
                "independently_verified": True
            }
        ]
    }


class PdfReconciliationTests(unittest.TestCase):
    def test_complete_final_report_passes(self):
        issues, summary = validator.inspect_report(valid_report())
        self.assertEqual(issues, [])
        self.assertEqual(summary["gate"], "PASS")
        self.assertEqual(summary["matches"], 1)
        self.assertEqual(summary["pages_reviewed"], 2)

    def test_mismatch_blocks_gate(self):
        report = valid_report()
        report["items"][0]["extracted_raw"] = "2345.6"
        issues, summary = validator.inspect_report(report)
        self.assertEqual(summary["gate"], "BLOCKED")
        self.assertEqual(summary["mismatches"], 1)
        self.assertTrue(any("raw value mismatch" in issue for issue in issues))

    def test_preliminary_blocks_standard_history_even_if_values_match(self):
        report = valid_report()
        report["document"]["edition_status"] = "PRELIMINARY"
        issues, summary = validator.inspect_report(report)
        self.assertEqual(summary["gate"], "BLOCKED")
        self.assertTrue(any("requires edition_status FINAL" in issue for issue in issues))

    def test_incomplete_page_coverage_blocks_gate(self):
        report = valid_report()
        report["pages_reviewed"] = [1]
        issues, summary = validator.inspect_report(report)
        self.assertTrue(any("page coverage incomplete" in issue for issue in issues))
        self.assertEqual(summary["gate"], "BLOCKED")

    def test_unverified_item_and_duplicate_ids_block_gate(self):
        report = valid_report()
        second = copy.deepcopy(report["items"][0])
        second["independently_verified"] = False
        report["items"].append(second)
        issues, summary = validator.inspect_report(report)
        self.assertTrue(any("independently_verified must be true" in issue for issue in issues))
        self.assertTrue(any("duplicate check_id" in issue for issue in issues))
        self.assertEqual(summary["gate"], "BLOCKED")

    def test_invalid_hash_is_rejected(self):
        report = valid_report()
        report["document"]["sha256"] = "not-a-hash"
        issues, summary = validator.inspect_report(report)
        self.assertTrue(any("sha256" in issue for issue in issues))
        self.assertEqual(summary["gate"], "BLOCKED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
