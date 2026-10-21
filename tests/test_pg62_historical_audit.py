from __future__ import annotations

import importlib.util
import sys
import unittest
from decimal import Decimal
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parents[1]
PDF_DIR = ROOT / "data" / "cme-pg62"
PARSER_PATH = ROOT / "scripts" / "parse_pg62.py"
spec = importlib.util.spec_from_file_location("pg62_audit_parser", PARSER_PATH)
if spec is None or spec.loader is None:
    raise ImportError(f"Cannot load PG62 parser at {PARSER_PATH}")
pg62 = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = pg62
spec.loader.exec_module(pg62)

# Historical audit anchors. Hashes are SHA-256 of the complete PDF bytes.
CASES = {
    "2026-10-12": {
        "file": "PG62_2026-10-12.pdf",
        "sha256": "118aa6deb4303558d548bc9edcc04154f2c68798ee34c831d6a0309703bcc57b",
        "rows": 27,
        "totals": {
            "volume_globex": "114665",
            "volume_pnt_pit": "1086",
            "open_interest": "392484",
            "oi_change": "-1090",
        },
    },
    "2026-10-13": {
        "file": "PG62_2026-10-13.pdf",
        "sha256": "114e5b1b2d238d85e3922462b65e66bd6204416a880a1e826d9079a71b1966ef",
        "rows": 27,
        "totals": {
            "volume_globex": "140217",
            "volume_pnt_pit": "2191",
            "open_interest": "396345",
            "oi_change": "3861",
        },
    },
    "2026-10-14": {
        "file": "PG62_2026-10-14.pdf",
        "sha256": "8f8e82715dfb06852e965117f88204b066017279a0d6c7354e60be1e7ab91b02",
        "rows": 27,
        "totals": {
            "volume_globex": "208359",
            "volume_pnt_pit": "2580",
            "open_interest": "399926",
            "oi_change": "3581",
        },
    },
}


def cell_value(row, field):
    cell = row[field]
    if cell.get("state") != "VALUE":
        return None
    return Decimal(cell["value"])


def totals_map(parsed):
    return {
        item["field"]: item["value"]
        for item in parsed["source_total"]["cells"]
    }


class PG62HistoricalAuditRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parsed = {}

    def parse_case(self, date):
        if date not in self.parsed:
            case = CASES[date]
            path = PDF_DIR / case["file"]
            self.assertTrue(path.is_file(), f"Missing source PDF: {path}")
            parsed = pg62.parse_pdf(path)
            self.parsed[date] = parsed
        return self.parsed[date]

    def test_pdf_identity_date_pages_and_edition(self):
        for date, case in CASES.items():
            with self.subTest(date=date):
                path = PDF_DIR / case["file"]
                self.assertEqual(pg62.sha256(path), case["sha256"])
                with pdfplumber.open(path) as pdf:
                    self.assertEqual(len(pdf.pages), 8)
                parsed = self.parse_case(date)
                self.assertEqual(parsed["trade_date"], date)
                self.assertEqual(parsed["bulletin"]["status"], "FINAL")
                self.assertEqual(parsed["source"]["sha256"], case["sha256"])

    def test_gc_row_count_contract_uniqueness_and_total_anchors(self):
        for date, case in CASES.items():
            with self.subTest(date=date):
                parsed = self.parse_case(date)
                rows = parsed["contracts"]
                self.assertEqual(len(rows), case["rows"])
                contracts = [row["contract"] for row in rows]
                self.assertEqual(len(contracts), len(set(contracts)))
                self.assertEqual(parsed["validation"]["status"], "PASS")
                self.assertEqual(
                    {item["field"] for item in parsed["validation"]["total_reconciliation"]},
                    set(case["totals"]),
                )
                for item in parsed["validation"]["total_reconciliation"]:
                    self.assertTrue(item["pass"], item)
                self.assertEqual(
                    {k: str(v) for k, v in totals_map(parsed).items()},
                    case["totals"],
                )

    def test_reported_settlement_change_matches_prior_final_pdf(self):
        previous = self.parse_case("2026-10-13")
        current = self.parse_case("2026-10-14")
        old_rows = {row["contract"]: row for row in previous["contracts"]}
        new_rows = {row["contract"]: row for row in current["contracts"]}
        self.assertEqual(set(old_rows), set(new_rows))

        checked = 0
        for contract, row in new_rows.items():
            with self.subTest(contract=contract):
                old_settlement = cell_value(old_rows[contract], "settlement")
                new_settlement = cell_value(row, "settlement")
                reported_change = cell_value(row, "price_change")
                self.assertIsNotNone(old_settlement, f"{contract}: prior settlement unresolved")
                self.assertIsNotNone(new_settlement, f"{contract}: current settlement unresolved")
                self.assertIsNotNone(reported_change, f"{contract}: reported change unresolved")
                self.assertEqual(
                    new_settlement - old_settlement,
                    reported_change,
                    f"{contract}: settlement change does not reconcile",
                )
                checked += 1
        self.assertEqual(checked, 27)

    def test_source_raw_line_contains_each_parsed_contract(self):
        # This is a parser-integrity assertion, not independent cell-level proof.
        for date in CASES:
            parsed = self.parse_case(date)
            for row in parsed["contracts"]:
                with self.subTest(date=date, contract=row["contract"]):
                    self.assertIn(row["contract"], row["source"]["raw_line"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
