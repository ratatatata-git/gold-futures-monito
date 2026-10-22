from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from validate_pg62_cell_reconciliation import FIELDS, validate_pg62_coverage


def report_fixture():
    fields = sorted(FIELDS)
    contracts = ["JAN27", "FEB27"]
    items = []
    for contract in contracts:
        for field in fields:
            raw = contract if field == "contract_code" else "1.00"
            items.append({
                "check_id": f"pg62-2026-10-14-{contract}-{field}",
                "page_number": 2,
                "locator": f"GC row {contract}, {field}",
                "field": field,
                "expected_raw": raw,
                "extracted_raw": raw,
                "independently_verified": True,
            })
    return {
        "schema_version": 1,
        "document": {
            "bulletin_type": "PG62", "bulletin_date": "2026-10-14",
            "edition_status": "FINAL", "sha256": "a" * 64, "page_count": 2,
            "source_url": "https://example.invalid/pg62",
            "retrieved_at": "2026-10-15T00:00:00Z",
        },
        "review": {
            "reviewer": "test reviewer", "reviewed_at": "2026-10-15T01:00:00Z",
            "method": "independent_manual_pdf",
        },
        "pages_reviewed": [1, 2],
        "page_review_checklist": [
            {"page_number": 1, "reviewed": True},
            {"page_number": 2, "reviewed": True},
        ],
        "items": items,
    }


class PG62CoverageGateTests(unittest.TestCase):
    def test_passes_complete_contract_field_matrix(self):
        issues, summary = validate_pg62_coverage(report_fixture(), expected_contract_count=2)
        self.assertEqual(issues, [])
        self.assertEqual(summary["gate"], "PASS")
        self.assertEqual(summary["checks"], 20)

    def test_blocks_missing_cell_even_if_remaining_cells_match(self):
        report = report_fixture()
        report["items"].pop()
        issues, _ = validate_pg62_coverage(report, expected_contract_count=2)
        self.assertTrue(any("expected exactly 20 cell checks" in issue for issue in issues))
        self.assertTrue(any("missing contract-field checks" in issue for issue in issues))

    def test_blocks_duplicate_cell_and_unreviewed_page(self):
        report = report_fixture()
        report["items"].append(copy.deepcopy(report["items"][0]))
        report["page_review_checklist"][0]["reviewed"] = False
        issues, _ = validate_pg62_coverage(report, expected_contract_count=2)
        self.assertTrue(any("duplicate contract-field check" in issue for issue in issues))
        self.assertTrue(any("every PDF page reviewed" in issue for issue in issues))

    def test_blocks_non_final_and_wrong_field_identity(self):
        report = report_fixture()
        report["document"]["edition_status"] = "PRELIMINARY"
        report["items"][0]["check_id"] = report["items"][0]["check_id"].replace(
            report["items"][0]["field"], "not-a-field"
        )
        issues, _ = validate_pg62_coverage(report, expected_contract_count=2)
        self.assertTrue(any("must be FINAL" in issue for issue in issues))
        self.assertTrue(any("suffix does not match" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main(verbosity=2)
