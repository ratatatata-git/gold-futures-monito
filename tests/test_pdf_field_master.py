import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import validate_pdf_field_master as validator  # noqa: E402


class PdfFieldMasterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.master = json.loads((ROOT / "data/definitions/pdf-field-master.json").read_text(encoding="utf-8"))

    def test_repository_master_has_valid_structure(self):
        result = validator.validate(self.master)
        self.assertEqual(result["gate"], "PASS", result["issues"])

    def test_duplicate_field_id_blocks(self):
        master = copy.deepcopy(self.master)
        master["field_definitions"].append(copy.deepcopy(master["field_definitions"][0]))
        result = validator.validate(master)
        self.assertEqual(result["gate"], "BLOCKED")
        self.assertTrue(any("duplicate field_id" in issue for issue in result["issues"]))

    def test_unknown_state_blocks(self):
        master = copy.deepcopy(self.master)
        master["field_definitions"][0]["allowed_states"].append("MAGIC")
        result = validator.validate(master)
        self.assertTrue(any("unknown state" in issue for issue in result["issues"]))

    def test_publishable_state_must_be_allowed(self):
        master = copy.deepcopy(self.master)
        master["field_definitions"][0]["publishable_when"] = ["SOURCE_NULL"]
        result = validator.validate(master)
        self.assertTrue(any("publishable_when contains a state not allowed" in issue for issue in result["issues"]))

    def test_single_evidence_group_blocks(self):
        master = copy.deepcopy(self.master)
        master["evidence_policy"]["minimum_distinct_evidence_groups_per_cell"] = 1
        result = validator.validate(master)
        self.assertTrue(any("at least 2" in issue for issue in result["issues"]))

    def test_layout_definition_cannot_be_independent_evidence(self):
        master = copy.deepcopy(self.master)
        master["evidence_policy"]["layout_definition_alone_is_independent_evidence"] = True
        result = validator.validate(master)
        self.assertTrue(any("must be false" in issue for issue in result["issues"]))

    def test_approved_profile_requires_complete_fingerprint(self):
        master = copy.deepcopy(self.master)
        master["layout_profiles"][0]["status"] = "APPROVED"
        result = validator.validate(master)
        self.assertTrue(any("incomplete fingerprint" in issue for issue in result["issues"]))
        self.assertTrue(any("lacks page geometry/count" in issue for issue in result["issues"]))

    def test_quarantine_must_block_promotion(self):
        master = copy.deepcopy(self.master)
        master["evidence_policy"]["quarantine_blocks_promotion"] = False
        result = validator.validate(master)
        self.assertTrue(any("quarantine_blocks_promotion must be true" in issue for issue in result["issues"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
