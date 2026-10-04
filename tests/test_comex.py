#!/usr/bin/env python3
"""Repository-level smoke/integration tests for COMEX PDFs."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import parse_pg62  # noqa: E402
import parse_pg64  # noqa: E402

PG62_DIR = ROOT / "data" / "cme-pg62"
PG64_DIR = ROOT / "data" / "cme-pg64"


class PG62RepositoryTests(unittest.TestCase):
    def test_all_pg62_pdfs_fail_closed_and_reconcile(self):
        pdfs = sorted(PG62_DIR.glob("*.pdf"))
        self.assertTrue(pdfs, f"No PG62 PDFs found in {PG62_DIR}")
        for pdf in pdfs:
            with self.subTest(pdf=pdf.name):
                d = parse_pg62.parse_pdf(pdf)
                self.assertEqual(d["dataset"], "PG62_GC_FUTURES")
                self.assertEqual(len(d["contracts"]), 28)
                self.assertEqual(d["validation"]["status"], "PASS")
                self.assertTrue(all(x["pass"] for x in d["validation"]["total_reconciliation"]))


class PG64RepositoryTests(unittest.TestCase):
    def test_all_pg64_pdfs_are_auditable_but_not_promoted(self):
        pdfs = sorted(PG64_DIR.glob("*.pdf"))
        self.assertTrue(pdfs, f"No PG64 PDFs found in {PG64_DIR}")
        for pdf in pdfs:
            with self.subTest(pdf=pdf.name):
                d = parse_pg64.audit(pdf)
                self.assertEqual(d["production_master_status"], "BLOCKED_DIAGNOSTIC_ONLY")
                self.assertGreater(d["candidate_strike_rows"], 0)
                self.assertTrue(d["pages_with_main_chain_header"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
