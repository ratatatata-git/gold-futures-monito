import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import validate_pdf_semantic_invariants as validator  # noqa: E402


class PdfSemanticInvariantTests(unittest.TestCase):
    def test_settlement_change_identity_passes(self):
        result = validator.inspect_identities([
            {
                "check_id": "synthetic-settlement-change",
                "kind": "SETTLEMENT_CHANGE",
                "status": "CHECKED",
                "current_settlement": "123.45",
                "previous_settlement": "120.00",
                "reported_change": "3.45",
            }
        ])
        self.assertEqual(result["gate"], "PASS")
        self.assertEqual(result["checked"], 1)

    def test_open_interest_change_identity_passes(self):
        result = validator.inspect_identities([
            {
                "check_id": "synthetic-oi-change",
                "kind": "OPEN_INTEREST_CHANGE",
                "status": "CHECKED",
                "current_open_interest": 1050,
                "previous_open_interest": 1000,
                "reported_change": 50,
            }
        ])
        self.assertEqual(result["gate"], "PASS")

    def test_mismatch_blocks(self):
        result = validator.inspect_identities([
            {
                "check_id": "synthetic-mismatch",
                "kind": "SETTLEMENT_CHANGE",
                "status": "CHECKED",
                "current_settlement": "123.45",
                "previous_settlement": "120.00",
                "reported_change": "3.44",
            }
        ])
        self.assertEqual(result["gate"], "BLOCKED")
        self.assertTrue(any("identity mismatch" in issue for issue in result["issues"]))

    def test_unresolved_blocks(self):
        result = validator.inspect_identities([
            {"check_id": "synthetic-unresolved", "kind": "SETTLEMENT_CHANGE", "status": "UNRESOLVED"}
        ])
        self.assertEqual(result["gate"], "BLOCKED")

    def test_not_applicable_requires_reason(self):
        result = validator.inspect_identities([
            {"check_id": "synthetic-na", "kind": "SETTLEMENT_CHANGE", "status": "NOT_APPLICABLE"}
        ])
        self.assertEqual(result["gate"], "BLOCKED")
        self.assertTrue(any("reason is required" in issue for issue in result["issues"]))

    def test_decimal_arithmetic_does_not_use_float_rounding(self):
        result = validator.inspect_identities([
            {
                "check_id": "synthetic-decimal",
                "kind": "SETTLEMENT_CHANGE",
                "status": "CHECKED",
                "current_settlement": "0.3",
                "previous_settlement": "0.1",
                "reported_change": "0.2",
            }
        ])
        self.assertEqual(result["gate"], "PASS")


if __name__ == "__main__":
    unittest.main(verbosity=2)
