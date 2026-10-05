#!/usr/bin/env python3
"""Integration checks for the current COMEX parser prototype."""

import importlib.util
from pathlib import Path
import unittest


# ============================================================
# Repository paths
# ============================================================

ROOT = Path(__file__).resolve().parents[1]

SCRIPTS_DIR = ROOT / "scripts"
PG62_DATA_DIR = ROOT / "data" / "cme-pg62"
PG64_DATA_DIR = ROOT / "data" / "cme-pg64"


# ============================================================
# Parser loader
# ============================================================

def load_parser(name: str, filename: str):
    """Load a parser from the repository's scripts directory."""

    path = SCRIPTS_DIR / filename

    if not path.exists():
        raise FileNotFoundError(
            f"Parser not found: {path}"
        )

    spec = importlib.util.spec_from_file_location(
        name,
        path,
    )

    if spec is None or spec.loader is None:
        raise ImportError(
            f"Cannot load parser: {path}"
        )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


pg62 = load_parser(
    "pg62v5",
    "parse_pg62_v5.py",
)

pg64 = load_parser(
    "pg64v5",
    "parse_pg64_v5.py",
)


# ============================================================
# PG62
# ============================================================

class PG62Integration(unittest.TestCase):

    def test_2026_09_23(self):
        """PG62 2026-09-23 FINAL."""

        pdf = (
            PG62_DATA_DIR
            / "PG62_2026-09-23.pdf"
        )

        if not pdf.exists():
            self.skipTest(
                f"fixture PDF not present: {pdf}"
            )

        data = pg62.parse_pdf(pdf)

        self.assertEqual(
            data["trade_date"],
            "2026-09-23",
        )

        self.assertEqual(
            len(data["contracts"]),
            28,
        )

        self.assertEqual(
            data["bulletin"]["status"],
            "FINAL",
        )

        reconciliation = data["validation"][
            "total_reconciliation"
        ]

        self.assertTrue(
            reconciliation,
            "TOTAL reconciliation result is empty",
        )

        self.assertTrue(
            all(
                item["pass"]
                for item in reconciliation
            ),
            f"TOTAL reconciliation failed: {reconciliation}",
        )

        self.assertEqual(
            {
                item["field"]
                for item in reconciliation
            },
            {
                "volume_globex",
                "volume_pnt_pit",
                "open_interest",
                "oi_change",
            },
        )

    def test_2026_09_25(self):
        """PG62 2026-09-25 PRELIMINARY."""

        pdf = (
            PG62_DATA_DIR
            / "PG62_2026-09-25.pdf"
        )

        if not pdf.exists():
            self.skipTest(
                f"fixture PDF not present: {pdf}"
            )

        data = pg62.parse_pdf(pdf)

        self.assertEqual(
            data["trade_date"],
            "2026-09-25",
        )

        self.assertEqual(
            len(data["contracts"]),
            28,
        )

        self.assertEqual(
            data["bulletin"]["status"],
            "PRELIMINARY",
        )

        reconciliation = data["validation"][
            "total_reconciliation"
        ]

        self.assertTrue(
            reconciliation,
            "TOTAL reconciliation result is empty",
        )

        self.assertTrue(
            all(
                item["pass"]
                for item in reconciliation
            ),
            f"TOTAL reconciliation failed: {reconciliation}",
        )


# ============================================================
# PG64
# ============================================================

class PG64Audit(unittest.TestCase):

    def test_audit_only_not_master(self):
        """
        PG64 is currently diagnostic/audit-only.

        It must not produce a production MASTER record.
        """

        pdf = (
            PG64_DATA_DIR
            / "PG64_2026-09-25.pdf"
        )

        if not pdf.exists():
            self.skipTest(
                f"fixture PDF not present: {pdf}"
            )

        data = pg64.audit(pdf)

        self.assertEqual(
            data["production_master_status"],
            "BLOCKED_DIAGNOSTIC_ONLY",
        )

        self.assertGreater(
            len(
                data["pages_with_main_chain_header"]
            ),
            0,
            "No main option-chain header pages detected",
        )

        self.assertGreater(
            data["candidate_strike_rows"],
            0,
            "No candidate strike rows detected",
        )

        self.assertTrue(
            any(
                "character/content-stream"
                in risk.lower()
                for risk in data["known_unhandled_risks"]
            ),
            "Expected character/content-stream "
            "risk was not reported",
        )


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)
