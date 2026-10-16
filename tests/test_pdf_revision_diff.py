import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import compare_pdf_revisions as compare  # noqa: E402


def fixture(digest, raw="100.0", edition="FINAL", page_count=1):
    manifest = {"schema_version": 1, "document": {
        "bulletin_type": "PG62", "bulletin_date": "2026-10-15", "edition_status": edition,
        "sha256": digest, "page_count": page_count},
        "processing_status": "RAW_REGISTERED_LOCAL_ONLY", "publication_approved": False}
    report = {"schema_version": 1, "document": {
        "bulletin_type": "PG62", "bulletin_date": "2026-10-15", "edition_status": edition,
        "sha256": digest, "page_count": page_count, "source_url": "https://example.invalid/synthetic",
        "retrieved_at": "2026-10-16T10:00:00Z"},
        "review": {"reviewer": "reviewer", "reviewed_at": "2026-10-16T12:00:00Z",
                   "method": "independent_manual_pdf"},
        "pages_reviewed": list(range(1, page_count + 1)),
        "items": [{"check_id": "settlement-gc", "page_number": 1, "locator": "page 1 / synthetic table",
                   "field": "settlement_raw", "expected_raw": raw, "extracted_raw": raw,
                   "independently_verified": True}]}
    return manifest, report


class ComparePdfRevisionsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.old_m, self.old_r = fixture("a" * 64)
        self.new_m, self.new_r = fixture("b" * 64, raw="101.0")
        self.paths = []
        for name, data in (("old-manifest.json", self.old_m), ("old-report.json", self.old_r),
                           ("new-manifest.json", self.new_m), ("new-report.json", self.new_r)):
            path = self.root / name
            path.write_text(json.dumps(data), encoding="utf-8")
            self.paths.append(path)

    def tearDown(self):
        self.temp.cleanup()

    def compare(self):
        return compare.compare_revisions(*self.paths)

    def test_reports_raw_value_differences_and_keeps_publication_blocked(self):
        result = self.compare()
        self.assertEqual(result["comparison_status"], "DIFF_READY")
        self.assertEqual(result["summary"]["changed_count"], 1)
        self.assertEqual(result["changed"][0]["differences"]["expected_raw"]["old"], "100.0")
        self.assertEqual(result["changed"][0]["differences"]["expected_raw"]["new"], "101.0")
        self.assertFalse(result["publication_approved"])

    def test_blocks_same_hash(self):
        self.new_m["document"]["sha256"] = self.old_m["document"]["sha256"]
        self.new_r["document"]["sha256"] = self.old_r["document"]["sha256"]
        self.paths[2].write_text(json.dumps(self.new_m), encoding="utf-8")
        self.paths[3].write_text(json.dumps(self.new_r), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "hashes are identical"):
            self.compare()

    def test_blocks_mismatched_bulletin_identity(self):
        self.new_m["document"]["bulletin_date"] = "2026-10-14"
        self.new_r["document"]["bulletin_date"] = "2026-10-14"
        self.paths[2].write_text(json.dumps(self.new_m), encoding="utf-8")
        self.paths[3].write_text(json.dumps(self.new_r), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "share bulletin_date"):
            self.compare()

    def test_blocks_manifest_report_hash_mismatch(self):
        self.new_r["document"]["sha256"] = "c" * 64
        self.paths[3].write_text(json.dumps(self.new_r), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "provenance mismatch for sha256"):
            self.compare()

    def test_blocks_unreviewed_report(self):
        self.new_r["pages_reviewed"] = []
        self.paths[3].write_text(json.dumps(self.new_r), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "reconciliation report is blocked"):
            self.compare()


if __name__ == "__main__":
    unittest.main(verbosity=2)
