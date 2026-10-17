from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pypdf import PdfWriter

from scripts.create_pdf_review_worksheet import build_worksheet


class PdfReviewWorksheetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.pdf = Path(self.temp.name) / "source.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        writer.add_blank_page(width=612, height=792)
        with self.pdf.open("wb") as handle:
            writer.write(handle)

    def build(self, **overrides):
        args = {
            "bulletin_type": "PG62",
            "bulletin_date": "2026-10-14",
            "edition_status": "FINAL",
            "source_url": "https://www.cmegroup.com/market-data/daily-bulletin.html",
            "retrieved_at": "2026-10-14T23:00:00Z",
        }
        args.update(overrides)
        return build_worksheet(self.pdf, **args)

    def test_template_records_hash_and_every_page_without_claiming_review(self):
        report = self.build()
        self.assertEqual(report["document"]["page_count"], 2)
        self.assertEqual(len(report["document"]["sha256"]), 64)
        self.assertEqual(report["pages_reviewed"], [])
        self.assertEqual([p["page_number"] for p in report["page_review_checklist"]], [1, 2])
        self.assertTrue(all(not p["reviewed"] for p in report["page_review_checklist"]))
        self.assertTrue(all(item["independently_verified"] is False for item in report["items"]))
        self.assertEqual(report["worksheet_status"], "INCOMPLETE_REVIEW_REQUIRED")

    def test_rejects_invalid_date_and_missing_source(self):
        with self.assertRaises(ValueError):
            self.build(bulletin_date="2026-02-31")
        with self.assertRaises(ValueError):
            self.build(source_url=" ")

    def test_rejects_unknown_bulletin_type_and_invalid_timestamp(self):
        with self.assertRaises(ValueError):
            self.build(bulletin_type="PG63")
        with self.assertRaises(ValueError):
            self.build(retrieved_at="yesterday")
        with self.assertRaises(ValueError):
            self.build(retrieved_at="2026-10-14T23:00:00")


if __name__ == "__main__":
    unittest.main()
