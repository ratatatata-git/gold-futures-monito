from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_pdf_audit_evidence_ledger import DEFAULT_LEDGER, validate_ledger


class PdfAuditEvidenceLedgerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger = json.loads(DEFAULT_LEDGER.read_text(encoding="utf-8"))

    def test_committed_ledger_is_structurally_valid(self):
        self.assertEqual(validate_ledger(self.ledger), [])

    def test_unknown_source_reference_fails(self):
        data = copy.deepcopy(self.ledger)
        data["evidence"][0]["source_ids"] = ["missing-source"]
        self.assertTrue(any("unknown source_id" in e for e in validate_ledger(data)))

    def test_reproducible_evidence_requires_command_and_artifacts(self):
        data = copy.deepcopy(self.ledger)
        data["evidence"][3].pop("command")
        errors = validate_ledger(data)
        self.assertTrue(any("requires a command" in e for e in errors))

    def test_invalid_source_sha256_fails(self):
        data = copy.deepcopy(self.ledger)
        data["sources"][0]["sha256"] = "not-a-hash"
        self.assertTrue(any("sha256" in e for e in validate_ledger(data)))

    def test_duplicate_evidence_id_fails(self):
        data = copy.deepcopy(self.ledger)
        data["evidence"][1]["evidence_id"] = data["evidence"][0]["evidence_id"]
        self.assertTrue(any("duplicate evidence_id" in e for e in validate_ledger(data)))

    def test_incomplete_evidence_is_not_mislabeled_as_reproducible(self):
        data = copy.deepcopy(self.ledger)
        item = next(e for e in data["evidence"] if e["status"] == "INCOMPLETE")
        item["command"] = "python some-command.py"
        self.assertTrue(any("incomplete evidence must not advertise" in e for e in validate_ledger(data)))


if __name__ == "__main__":
    unittest.main()
