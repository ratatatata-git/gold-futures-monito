import json
import sys
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfWriter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import register_pdf_revision as register  # noqa: E402


class PdfRevisionManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.pdf = self.root / "sample.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=300, height=400)
        writer.add_blank_page(width=300, height=400)
        with self.pdf.open("wb") as handle:
            writer.write(handle)

    def tearDown(self):
        self.temp.cleanup()

    def build(self, **kwargs):
        defaults = {
            "pdf_path": self.pdf,
            "bulletin_type": "PG62",
            "bulletin_date": "2026-10-15",
            "edition_status": "FINAL",
            "source_url": "https://example.invalid/synthetic-pdf",
            "retrieved_at": "2026-10-16T10:00:00Z",
            "parent_manifest_path": None,
        }
        defaults.update(kwargs)
        return register.build_manifest(**defaults)

    def test_registers_hash_page_count_and_fail_closed_publication_state(self):
        manifest = self.build()
        self.assertEqual(manifest["document"]["sha256"], register.sha256_file(self.pdf))
        self.assertEqual(manifest["document"]["page_count"], 2)
        self.assertEqual(manifest["processing_status"], "RAW_REGISTERED_LOCAL_ONLY")
        self.assertEqual(manifest["publication_status"], "NOT_REVIEWED")
        self.assertFalse(manifest["publication_approved"])
        self.assertEqual(manifest["revision"]["relation"], "initial_registration")

    def test_parent_manifest_tracks_hash_without_overwriting(self):
        parent = self.build()
        parent["document"]["sha256"] = "b" * 64
        parent_path = self.root / "parent.json"
        parent_path.write_text(json.dumps(parent), encoding="utf-8")
        manifest = self.build(parent_manifest_path=parent_path)
        self.assertEqual(manifest["revision"]["relation"], "new_revision_candidate")
        self.assertEqual(manifest["revision"]["parent"]["sha256"], "b" * 64)

    def test_parent_must_match_bulletin_identity(self):
        parent = self.build()
        parent["document"]["bulletin_date"] = "2026-10-14"
        parent_path = self.root / "parent.json"
        parent_path.write_text(json.dumps(parent), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "same bulletin type and date"):
            self.build(parent_manifest_path=parent_path)

    def test_same_hash_cannot_be_registered_as_new_revision(self):
        parent = self.build()
        parent_path = self.root / "parent.json"
        parent_path.write_text(json.dumps(parent), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "matches parent"):
            self.build(parent_manifest_path=parent_path)

    def test_unknown_edition_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "edition_status"):
            self.build(edition_status="LATEST")

    def test_non_pdf_is_rejected(self):
        text_file = self.root / "sample.txt"
        text_file.write_text("not a PDF", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "extension"):
            self.build(pdf_path=text_file)


if __name__ == "__main__":
    unittest.main(verbosity=2)
