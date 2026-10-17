import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import validate_pdf_parser_provenance as provenance  # noqa: E402


def fixture(bulletin_type="PG62", edition="FINAL"):
    dataset = "PG62_GC_FUTURES" if bulletin_type == "PG62" else "PG64_GOLD_OPTIONS"
    manifest = {
        "schema_version": 1,
        "document": {
            "bulletin_type": bulletin_type,
            "bulletin_date": "2026-10-15",
            "edition_status": edition,
            "sha256": "a" * 64,
            "page_count": 2,
        },
        "processing_status": "RAW_REGISTERED_LOCAL_ONLY",
        "publication_approved": False,
    }
    artifact = {
        "dataset": dataset,
        "trade_date": "2026-10-15",
        "source": {"sha256": "a" * 64},
        "bulletin": {"status": edition} if bulletin_type == "PG62" else {"status_candidates": [edition]},
        "page_count": 2,
        "parser_version": "synthetic",
    }
    if bulletin_type == "PG62":
        artifact["validation"] = {"status": "PASS"}
    else:
        artifact["production_master_status"] = "DIAGNOSTIC_ONLY"
    return manifest, artifact


class PdfParserProvenanceTests(unittest.TestCase):
    def test_pg62_provenance_match_does_not_approve_accuracy(self):
        manifest, artifact = fixture()
        result = provenance.verify(manifest, artifact)
        self.assertEqual(result["check_status"], "PROVENANCE_MATCH")
        self.assertEqual(result["accuracy_gate"], "NOT_EVALUATED")
        self.assertFalse(result["publication_approved"])

    def test_pg64_is_explicitly_diagnostic_only(self):
        manifest, artifact = fixture("PG64")
        result = provenance.verify(manifest, artifact)
        self.assertEqual(result["parser_mode"], "diagnostic audit only")
        self.assertFalse(result["publication_approved"])

    def test_blocks_hash_mismatch(self):
        manifest, artifact = fixture()
        artifact["source"]["sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "sha256"):
            provenance.verify(manifest, artifact)

    def test_blocks_date_mismatch(self):
        manifest, artifact = fixture()
        artifact["trade_date"] = "2026-10-14"
        with self.assertRaisesRegex(ValueError, "trade_date"):
            provenance.verify(manifest, artifact)

    def test_blocks_ambiguous_pg64_edition(self):
        manifest, artifact = fixture("PG64")
        artifact["bulletin"]["status_candidates"] = ["FINAL", "PRELIMINARY"]
        with self.assertRaisesRegex(ValueError, "status_candidates"):
            provenance.verify(manifest, artifact)

    def test_blocks_page_count_mismatch(self):
        manifest, artifact = fixture()
        artifact["page_count"] = 3
        with self.assertRaisesRegex(ValueError, "page_count"):
            provenance.verify(manifest, artifact)


if __name__ == "__main__":
    unittest.main(verbosity=2)
