from __future__ import annotations

import re
import unittest
from decimal import Decimal
from pathlib import Path

from test_pg62_historical_audit import CASES, PDF_DIR, PG62HistoricalAuditRegressionTests, pg62


NULL_MARKERS = {"", "----", "---", "--", "-", "—", "–"}
SIGNED_FIELDS = {"price_change", "oi_change"}
SCALAR_FIELDS = (
    "open",
    "settlement",
    "price_change",
    "volume_globex",
    "volume_pnt_pit",
    "open_interest",
    "oi_change",
)
NUMBER = re.compile(r"^[+-]?(?:\d+(?:,\d{3})*(?:\.\d+)?|\.\d+)$")


def independently_interpret_scalar(raw: str, signed: bool) -> tuple[str, str | None]:
    """Small test-side grammar, intentionally not calling parser.state/parse_*."""
    token = re.sub(r"\s+", "", raw).upper()
    if token in NULL_MARKERS:
        return ("EMPTY" if token == "" else "SOURCE_NULL", None)
    if signed and token == "UNCH":
        return "VALUE", "0"
    if token == "NEW":
        return "PARSER_ERROR", None
    if token.startswith("+"):
        token = token[1:]
    if not NUMBER.fullmatch(token):
        return "PARSER_ERROR", None
    try:
        value = Decimal(token.replace(",", ""))
    except Exception:
        return "PARSER_ERROR", None
    return "VALUE", format(value, "f")


class PG62CellStateRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parsed_by_date = {}
        for date, case in CASES.items():
            path = PDF_DIR / case["file"]
            cls.parsed_by_date[date] = pg62.parse_pdf(path)

    def test_every_scalar_cell_state_and_value_agree_with_raw_token(self):
        """Checks state/value semantics for all 81 rows; not an independent PDF column audit."""
        checked = 0
        for date, parsed in self.parsed_by_date.items():
            for row in parsed["contracts"]:
                for field in SCALAR_FIELDS:
                    cell = row[field]
                    expected_state, expected_value = independently_interpret_scalar(
                        cell["raw"], field in SIGNED_FIELDS
                    )
                    with self.subTest(date=date, contract=row["contract"], field=field, raw=cell["raw"]):
                        self.assertEqual(cell["state"], expected_state)
                        self.assertEqual(cell["value"], expected_value)
                    checked += 1
        self.assertEqual(checked, 3 * 27 * len(SCALAR_FIELDS))

    def test_hilo_cells_preserve_shared_raw_source_and_numeric_values(self):
        """High/low are two interpretations of one slash-delimited source cell."""
        checked = 0
        for date, parsed in self.parsed_by_date.items():
            for row in parsed["contracts"]:
                high, low = row["high"], row["low"]
                with self.subTest(date=date, contract=row["contract"]):
                    self.assertEqual(high["raw"], low["raw"])
                    raw = re.sub(r"\s+", "", high["raw"]).upper()
                    if raw in NULL_MARKERS:
                        self.assertEqual(high["state"], "SOURCE_NULL" if raw else "EMPTY")
                        self.assertEqual(low["state"], high["state"])
                        self.assertIsNone(high["value"])
                        self.assertIsNone(low["value"])
                    else:
                        parts = raw.split("/")
                        self.assertLessEqual(len(parts), 2)
                        for cell, part in zip((high, low), (parts + [""] * 2)[:2]):
                            if not part or part in {"----", "---", "--", "-", "—", "–"}:
                                self.assertIsNone(cell["value"])
                            else:
                                numeric = re.sub(r"[ABPRN]$", "", part)
                                if NUMBER.fullmatch(numeric):
                                    self.assertEqual(cell["value"], format(Decimal(numeric.replace(",", "")), "f"))
                checked += 1
        self.assertEqual(checked, 3 * 27)


if __name__ == "__main__":
    unittest.main(verbosity=2)
