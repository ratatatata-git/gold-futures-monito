#!/usr/bin/env python3
"""
Integration checks for the current COMEX parser prototype.

Repository layout:

    scripts/
        parse_pg62_v5.py
        parse_pg64_v5.py

    data/
        cme-pg62/
            PG62_YYYY-MM-DD.pdf
        cme-pg64/
            PG64_YYYY-MM-DD.pdf

    tests/
        test_comex_v5.py
"""

import importlib.util
from pathlib import Path
import unittest


# ----------------------------------------------------------------------
# Repository paths
# ----------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]

SCRIPTS_DIR = ROOT / "scripts"
PG62_DATA_DIR = ROOT / "data" / "cme-pg62"
PG64_DATA_DIR = ROOT / "data" / "cme-pg64"


# ----------------------------------------------------------------------
# Dynamic parser loader
# ----------------------------------------------------------------------

def load_parser(name: str, filename: str):
    """
    Load a parser module from scripts/.

    This deliberately does not rely on the current working directory.
    GitHub Actions, local pytest, and IDE execution therefore all resolve
    the parser from the same repository-relative location.
    """
    path = SCRIPTS_DIR / filename

    if not path.exists():
        raise FileNotFoundError(
            f"Parser not found: {path}"
        )

    spec = importlib.util.spec_from_file_location(name, path)

    if spec is None or spec.loader is None:
        raise ImportError(
            f"Cannot create import specification for: {path}"
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


# ----------------------------------------------------------------------
# PG62 integration tests
# ----------------------------------------------------------------------

class PG62Integration(unittest.TestCase):

    def test_2026_09_23(self):
        """
        PG62 2026-09-23

        Expected:
        - trade date = 2026-09-23
        - 28 GC contracts
        - FINAL bulletin
        - TOTAL reconciliation passes
        """
        p = PG62_DATA_DIR / "PG62_2026-09-23.pdf"

        if not p.exists():
            self.skipTest(
                f"fixture PDF not present: {p}"
            )

        d = pg62.parse_pdf(p)

        self.assertEqual(
            d["trade_date"],
            "2026-09-23",
        )

        self.assertEqual(
            len(d["contracts"]),
            28,
        )

        self.assertEqual(
            d["bulletin"]["status"],
            "FINAL",
        )

        reconciliation = d["validation"]["total_reconciliation"]

        self.assertTrue(
            reconciliation,
            "TOTAL reconciliation result is empty",
        )

        self.assertTrue(
            all(x["pass"] for x in reconciliation),
            f"TOTAL reconciliation failed: {reconciliation}",
        )

        self.assertEqual(
            {x["field"] for x in reconciliation},
            {
                "volume_globex",
                "volume_pnt_pit",
                "open_interest",
                "oi_change",
            },
        )

    def test_2026_09_25(self):
        """
        PG62 2026-09-25

        Expected:
        - trade date = 2026-09-25
        - 28 GC contracts
        - PRELIMINARY bulletin
        - TOTAL reconciliation passes
        """
        p = PG62_DATA_DIR / "PG62_2026-09-25.pdf"

        if not p.exists():
            self.skipTest(
                f"fixture PDF not present: {p}"
            )

        d = pg62.parse_pdf(p)

        self.assertEqual(
            d["trade_date"],
            "2026-09-25",
        )

        self.assertEqual(
            len(d["contracts"]),
            28,
        )

        self.assertEqual(
            d["bulletin"]["status"],
            "PRELIMINARY",
        )

        reconciliation = d["validation"]["total_reconciliation"]

        self.assertTrue(
            reconciliation,
            "TOTAL reconciliation result is empty",
        )

        self.assertTrue(
            all(x["pass"] for x in reconciliation),
            f"TOTAL reconciliation failed: {reconciliation}",
        )


# ----------------------------------------------------------------------
# PG64 audit tests
# ----------------------------------------------------------------------

class PG64Audit(unittest.TestCase):

    def test_audit_only_not_master(self):
        """
        PG64 remains diagnostic/audit-only.

        It must NOT produce a production MASTER record yet.
        """
        p = PG64_DATA_DIR / "PG64_2026-09-25.pdf"

        if not p.exists():
            self.skipTest(
                f"fixture PDF not present: {p}"
            )

        d = pg64.audit(p)

        self.assertEqual(
            d["production_master_status"],
            "BLOCKED_DIAGNOSTIC_ONLY",
        )

        self.assertGreater(
            len(d["pages_with_main_chain_header"]),
            0,
            "No main option-chain header pages detected",
        )

        self.assertGreater(
            d["candidate_strike_rows"],
            0,
            "No candidate strike rows detected",
        )

        self.assertTrue(
            any(
                "character/content-stream" in x.lower()
                for x in d["known_unhandled_risks"]
            ),
            "Expected character/content-stream risk was not reported",
        )


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
