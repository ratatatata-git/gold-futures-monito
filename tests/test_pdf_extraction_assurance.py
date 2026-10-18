import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import validate_pdf_extraction_assurance as gate  # noqa: E402


def evidence():
    return [
        {"group": "layout", "reference": "synthetic-header-anchor", "result": "column location matches"},
        {"group": "visual", "reference": "synthetic-rendered-page-review", "result": "value independently confirmed"},
    ]


def valid_manifest():
    return {
        "schema_version": 1,
        "source": {"sha256": "a" * 64, "page_count": 1},
        "fingerprint": {"bulletin": "PG62", "layout": "synthetic-v1", "header": "SETTLEMENT"},
        "definitions": [
            {
                "definition_id": "pg62-synthetic-v1",
                "fingerprint": {"bulletin": "PG62", "layout": "synthetic-v1", "header": "SETTLEMENT"},
            }
        ],
        "tokens": [
            {"token_id": "p1-c1", "text": "SYNTHETIC"},
            {"token_id": "p1-c2", "text": "123"},
        ],
        "assignments": [
            {"token_id": "p1-c1", "disposition": "CELL", "cell_id": "contract"},
            {"token_id": "p1-c2", "disposition": "CELL", "cell_id": "settlement"},
        ],
        "cells": [
            {"cell_id": "contract", "value_status": "RESOLVED", "publishable": True, "evidence": evidence()},
            {"cell_id": "settlement", "value_status": "RESOLVED", "publishable": True, "evidence": evidence()},
        ],
    }


class PdfExtractionAssuranceTests(unittest.TestCase):
    def test_complete_synthetic_manifest_passes(self):
        result = gate.inspect_manifest(valid_manifest())
        self.assertEqual(result["gate"], "PASS")
        self.assertEqual(result["selected_definition"], "pg62-synthetic-v1")

    def test_unassigned_token_blocks(self):
        manifest = valid_manifest()
        manifest["assignments"].pop()
        result = gate.inspect_manifest(manifest)
        self.assertEqual(result["gate"], "BLOCKED")
        self.assertTrue(any("unassigned" in issue for issue in result["issues"]))

    def test_double_assigned_token_blocks(self):
        manifest = valid_manifest()
        manifest["assignments"].append(copy.deepcopy(manifest["assignments"][0]))
        result = gate.inspect_manifest(manifest)
        self.assertTrue(any("assigned 2 times" in issue for issue in result["issues"]))

    def test_unknown_token_reference_blocks(self):
        manifest = valid_manifest()
        manifest["assignments"][0]["token_id"] = "not-in-inventory"
        result = gate.inspect_manifest(manifest)
        self.assertTrue(any("unknown token_id" in issue for issue in result["issues"]))
        self.assertTrue(any("unassigned" in issue for issue in result["issues"]))

    def test_explicit_ignore_requires_reason(self):
        manifest = valid_manifest()
        manifest["assignments"][0] = {"token_id": "p1-c1", "disposition": "EXPLICIT_IGNORE"}
        result = gate.inspect_manifest(manifest)
        self.assertTrue(any("reason is required" in issue for issue in result["issues"]))

    def test_quarantine_blocks_promotion(self):
        manifest = valid_manifest()
        manifest["assignments"][0] = {
            "token_id": "p1-c1",
            "disposition": "QUARANTINE",
            "reason": "synthetic ambiguous glyph",
        }
        result = gate.inspect_manifest(manifest)
        self.assertEqual(result["gate"], "BLOCKED")
        self.assertTrue(any("promotion is blocked" in issue for issue in result["issues"]))

    def test_one_layout_evidence_group_is_insufficient(self):
        manifest = valid_manifest()
        manifest["cells"][0]["evidence"] = [
            {"group": "layout", "reference": "same-definition", "result": "matches"}
        ]
        result = gate.inspect_manifest(manifest)
        self.assertTrue(any("two distinct evidence groups" in issue for issue in result["issues"]))
        self.assertTrue(any("independent corroboration" in issue for issue in result["issues"]))

    def test_unresolved_value_cannot_be_publishable(self):
        manifest = valid_manifest()
        manifest["cells"][0]["value_status"] = "UNRESOLVED"
        result = gate.inspect_manifest(manifest)
        self.assertTrue(any("UNRESOLVED values cannot be publishable" in issue for issue in result["issues"]))

    def test_dangling_cell_reference_blocks(self):
        manifest = valid_manifest()
        manifest["assignments"][0]["cell_id"] = "missing-cell"
        result = gate.inspect_manifest(manifest)
        self.assertTrue(any("cell_id absent from cells" in issue for issue in result["issues"]))

    def test_zero_definition_matches_fail_closed(self):
        manifest = valid_manifest()
        manifest["fingerprint"]["layout"] = "unrecognized"
        result = gate.inspect_manifest(manifest)
        self.assertTrue(any("matched zero definitions" in issue for issue in result["issues"]))

    def test_multiple_definition_matches_fail_closed(self):
        manifest = valid_manifest()
        manifest["definitions"].append(copy.deepcopy(manifest["definitions"][0]))
        result = gate.inspect_manifest(manifest)
        self.assertTrue(any("matched multiple definitions" in issue for issue in result["issues"]))

    def test_duplicate_token_inventory_ids_block(self):
        manifest = valid_manifest()
        manifest["tokens"].append(copy.deepcopy(manifest["tokens"][0]))
        result = gate.inspect_manifest(manifest)
        self.assertTrue(any("token inventory contains duplicate" in issue for issue in result["issues"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
